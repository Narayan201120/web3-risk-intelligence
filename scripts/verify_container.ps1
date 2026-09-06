param(
    [string]$Image = "web3-risk-intelligence:local"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required to verify the container image."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker is installed but the Docker daemon is not available."
}

docker build --tag $Image .
if ($LASTEXITCODE -ne 0) {
    throw "Container build failed."
}

docker run --rm --entrypoint python $Image -m pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "Container test execution failed."
}

Write-Output "Container verification passed: $Image"
