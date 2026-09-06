[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [Parameter(Mandatory = $true)]
    [string]$BucketName,

    [string]$Region = "asia-south1",
    [string]$SchedulerRegion = "asia-south1",
    [string]$Repository = "web3-risk-intelligence",
    [string]$ImageName = "risk-intelligence",
    [string]$BatchJobName = "web3-risk-intelligence-batch",
    [string]$SentinelJobName = "web3-risk-intelligence-sentinel",
    [string]$DashboardServiceName = "web3-risk-intelligence-dashboard",
    [string]$RuntimeServiceAccountName = "web3-risk-runtime",
    [string]$DashboardServiceAccountName = "web3-risk-dashboard",
    [string]$SchedulerServiceAccountName = "web3-risk-scheduler",
    [string]$BatchSchedule = "0 * * * *",
    [string]$SentinelSchedule = "*/5 * * * *",
    [string]$WebhookSecretName,
    [switch]$PublicDashboard,
    [switch]$Plan,
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

if ($Plan -and $Apply) {
    throw "Choose either -Plan or -Apply, not both."
}

if (-not $Plan -and -not $Apply) {
    $Plan = $true
}

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimeServiceAccount = "$RuntimeServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$dashboardServiceAccount = "$DashboardServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$schedulerServiceAccount = "$SchedulerServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$imageTag = (git -C $projectRoot rev-parse --short HEAD 2>$null).Trim()
if (-not $imageTag) {
    $imageTag = Get-Date -Format "yyyyMMddHHmmss"
}
$image = "$Region-docker.pkg.dev/$ProjectId/$Repository/$ImageName`:$imageTag"

function Invoke-Gcloud {
    param([string[]]$Arguments)

    Write-Output ("gcloud " + ($Arguments -join " "))
    & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud command failed with exit code $LASTEXITCODE."
    }
}

function Test-GcloudResource {
    param([string[]]$Arguments)

    & gcloud @Arguments 1>$null 2>$null
    return $LASTEXITCODE -eq 0
}

function Ensure-ServiceAccount {
    param(
        [string]$Name,
        [string]$Email,
        [string]$DisplayName
    )

    if (-not (Test-GcloudResource @("iam", "service-accounts", "describe", $Email, "--project=$ProjectId"))) {
        Invoke-Gcloud @(
            "iam", "service-accounts", "create", $Name,
            "--project=$ProjectId",
            "--display-name=$DisplayName"
        )
    }
}

function Ensure-SchedulerJob {
    param(
        [string]$Name,
        [string]$Schedule,
        [string]$TargetJobName
    )

    $uri = "https://run.googleapis.com/v2/projects/$ProjectId/locations/$Region/jobs/${TargetJobName}:run"
    $arguments = @(
        "scheduler", "jobs",
        $(if (Test-GcloudResource @("scheduler", "jobs", "describe", $Name, "--location=$SchedulerRegion", "--project=$ProjectId")) { "update" } else { "create" }),
        "http", $Name,
        "--project=$ProjectId",
        "--location=$SchedulerRegion",
        "--schedule=$Schedule",
        "--time-zone=UTC",
        "--uri=$uri",
        "--http-method=POST",
        "--oauth-service-account-email=$schedulerServiceAccount"
    )
    Invoke-Gcloud $arguments
}

function Add-SecretArguments {
    if (-not $WebhookSecretName) {
        return @()
    }
    if (-not (Test-GcloudResource @("secrets", "describe", $WebhookSecretName, "--project=$ProjectId"))) {
        throw "Webhook secret '$WebhookSecretName' does not exist. Create it separately before deployment."
    }
    return @(
        "--set-secrets",
        "RISK_ALERT_WEBHOOK_URL=${WebhookSecretName}:latest,RISK_SENTINEL_WEBHOOK_URL=${WebhookSecretName}:latest"
    )
}

function Show-Plan {
    Write-Output "GCP deployment plan (no cloud changes)"
    Write-Output "Project: $ProjectId"
    Write-Output "Region: $Region"
    Write-Output "Bucket: gs://$BucketName"
    Write-Output "Image: $image"
    Write-Output "Batch job: $BatchJobName ($BatchSchedule UTC)"
    Write-Output "Sentinel job: $SentinelJobName ($SentinelSchedule UTC)"
    Write-Output "Dashboard service: $DashboardServiceName"
    Write-Output "Dashboard access: $(if ($PublicDashboard) { 'public' } else { 'authenticated' })"
    Write-Output "Webhook secret: $(if ($WebhookSecretName) { $WebhookSecretName } else { 'not configured' })"
    Write-Output "`nApply requires an authenticated gcloud account with permission to manage:"
    Write-Output "- Artifact Registry and Cloud Build"
    Write-Output "- Cloud Run Jobs and Services"
    Write-Output "- Cloud Storage bucket and IAM bindings"
    Write-Output "- Cloud Scheduler jobs"
    Write-Output "- Service accounts and service-account impersonation"
    Write-Output "- Secret Manager access when -WebhookSecretName is supplied"
}

if ($Plan) {
    Show-Plan
    exit 0
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud is required for -Apply. Install Google Cloud CLI and authenticate it first."
}

$activeAccount = (& gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null).Trim()
if (-not $activeAccount) {
    throw "No active gcloud account is configured. Run 'gcloud auth login' first."
}

Write-Output "Applying GCP deployment as $activeAccount"
Push-Location $projectRoot
try {
    Invoke-Gcloud @(
        "services", "enable",
        "run.googleapis.com",
        "artifactregistry.googleapis.com",
        "cloudbuild.googleapis.com",
        "storage.googleapis.com",
        "cloudscheduler.googleapis.com",
        "iam.googleapis.com",
        "secretmanager.googleapis.com",
        "--project=$ProjectId"
    )

    if (-not (Test-GcloudResource @("storage", "buckets", "describe", "gs://$BucketName", "--project=$ProjectId"))) {
        Invoke-Gcloud @(
            "storage", "buckets", "create", "gs://$BucketName",
            "--project=$ProjectId",
            "--location=$Region",
            "--uniform-bucket-level-access"
        )
    }

    if (-not (Test-GcloudResource @("artifacts", "repositories", "describe", $Repository, "--location=$Region", "--project=$ProjectId"))) {
        Invoke-Gcloud @(
            "artifacts", "repositories", "create", $Repository,
            "--repository-format=docker",
            "--location=$Region",
            "--project=$ProjectId",
            "--description=Web3 Risk Intelligence container images"
        )
    }

    Ensure-ServiceAccount $RuntimeServiceAccountName $runtimeServiceAccount "Web3 Risk Intelligence runtime"
    Ensure-ServiceAccount $DashboardServiceAccountName $dashboardServiceAccount "Web3 Risk Intelligence dashboard"
    Ensure-ServiceAccount $SchedulerServiceAccountName $schedulerServiceAccount "Web3 Risk Intelligence scheduler"

    Invoke-Gcloud @(
        "storage", "buckets", "add-iam-policy-binding", "gs://$BucketName",
        "--project=$ProjectId",
        "--member=serviceAccount:$runtimeServiceAccount",
        "--role=roles/storage.objectUser"
    )
    Invoke-Gcloud @(
        "storage", "buckets", "add-iam-policy-binding", "gs://$BucketName",
        "--project=$ProjectId",
        "--member=serviceAccount:$dashboardServiceAccount",
        "--role=roles/storage.objectViewer"
    )

    $projectNumber = (& gcloud projects describe $ProjectId --format="value(projectNumber)" 2>$null).Trim()
    if (-not $projectNumber) {
        throw "Could not resolve the project number for $ProjectId."
    }
    $cloudBuildServiceAccount = "$projectNumber@cloudbuild.gserviceaccount.com"
    Invoke-Gcloud @(
        "artifacts", "repositories", "add-iam-policy-binding", $Repository,
        "--location=$Region",
        "--project=$ProjectId",
        "--member=serviceAccount:$cloudBuildServiceAccount",
        "--role=roles/artifactregistry.writer"
    )

    Invoke-Gcloud @("builds", "submit", "--project=$ProjectId", "--tag=$image", ".")

    $dataVolume = "mount-path=/app/data,type=cloud-storage,bucket=$BucketName,readonly=false,mount-options=only-dir=data;uid=1000;gid=1000"
    $reportsVolume = "mount-path=/app/reports,type=cloud-storage,bucket=$BucketName,readonly=false,mount-options=only-dir=reports;uid=1000;gid=1000"
    $readOnlyReportsVolume = "mount-path=/app/reports,type=cloud-storage,bucket=$BucketName,readonly=true,mount-options=only-dir=reports;uid=1000;gid=1000"
    $secretArguments = Add-SecretArguments

    Invoke-Gcloud (@(
        "run", "jobs", "deploy", $BatchJobName,
        "--project=$ProjectId",
        "--region=$Region",
        "--image=$image",
        "--service-account=$runtimeServiceAccount",
        "--tasks=1",
        "--parallelism=1",
        "--max-retries=1",
        "--task-timeout=1h",
        "--add-volume", $dataVolume,
        "--add-volume", $reportsVolume
    ) + $secretArguments)

    Invoke-Gcloud (@(
        "run", "jobs", "deploy", $SentinelJobName,
        "--project=$ProjectId",
        "--region=$Region",
        "--image=$image",
        "--service-account=$runtimeServiceAccount",
        "--command=python",
        "--args=-m,src.monitoring.risk_sentinel",
        "--tasks=1",
        "--parallelism=1",
        "--max-retries=1",
        "--task-timeout=10m",
        "--add-volume", $dataVolume,
        "--add-volume", $reportsVolume
    ) + $secretArguments)

    $dashboardAccess = if ($PublicDashboard) { "--allow-unauthenticated" } else { "--no-allow-unauthenticated" }
    Invoke-Gcloud @(
        "run", "deploy", $DashboardServiceName,
        "--project=$ProjectId",
        "--region=$Region",
        "--image=$image",
        "--service-account=$dashboardServiceAccount",
        "--execution-environment=gen2",
        "--port=8080",
        "--command=streamlit",
        "--args=run,src/dashboard/app.py,--server.address=0.0.0.0,--server.port=8080",
        "--add-volume", $readOnlyReportsVolume,
        $dashboardAccess
    )

    Invoke-Gcloud @(
        "run", "jobs", "add-iam-policy-binding", $BatchJobName,
        "--project=$ProjectId",
        "--region=$Region",
        "--member=serviceAccount:$schedulerServiceAccount",
        "--role=roles/run.invoker"
    )
    Invoke-Gcloud @(
        "run", "jobs", "add-iam-policy-binding", $SentinelJobName,
        "--project=$ProjectId",
        "--region=$Region",
        "--member=serviceAccount:$schedulerServiceAccount",
        "--role=roles/run.invoker"
    )

    Ensure-SchedulerJob "${BatchJobName}-schedule" $BatchSchedule $BatchJobName
    Ensure-SchedulerJob "${SentinelJobName}-schedule" $SentinelSchedule $SentinelJobName

    Write-Output "Deployment completed."
    Write-Output "Dashboard service: $DashboardServiceName"
    Write-Output "Batch schedule: $BatchSchedule UTC"
    Write-Output "Sentinel schedule: $SentinelSchedule UTC"
}
finally {
    Pop-Location
}
