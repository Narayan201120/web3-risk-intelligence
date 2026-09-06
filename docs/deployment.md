# Deployment and Operations

This project is deliberately runnable without cloud credentials. The local
pipeline is the reference implementation; a cloud deployment should preserve
the same raw -> processed -> analytics -> dashboard contract.

## Local release checklist

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest
python src\run_pipeline.py
python src\quality\check_outputs.py
streamlit run src\dashboard\app.py
```

## Runtime container

The repository includes a production-shaped container image. Its default
command runs the batch pipeline, which is the command a scheduled Cloud Run
Job should execute:

```powershell
docker build --tag web3-risk-intelligence:local .
docker run --rm --env-file .env web3-risk-intelligence:local
```

The image runs as a non-root user and does not include local data, reports,
virtual environments, or credentials. Verify the image and its test suite with:

```powershell
.\scripts\verify_container.ps1
```

For a dashboard service, override the image command and provide published
report storage to the service rather than running a second ingestion pipeline:

```powershell
streamlit run src/dashboard/app.py --server.address=0.0.0.0 --server.port=8080
```

The container build is also checked by GitHub Actions. Cloud deployment still
requires a GCP project, registry, service account, and secret configuration.

## GCP deployment script

The repository includes an idempotent PowerShell deployment script. It is a
non-mutating plan by default:

```powershell
.\scripts\deploy_gcp.ps1 -Plan `
  -ProjectId YOUR_PROJECT_ID `
  -BucketName YOUR_UNIQUE_BUCKET_NAME
```

Apply the plan only after `gcloud auth login` and project permissions have been
verified:

```powershell
.\scripts\deploy_gcp.ps1 -Apply `
  -ProjectId YOUR_PROJECT_ID `
  -BucketName YOUR_UNIQUE_BUCKET_NAME
```

The script builds and pushes the image, creates or updates the batch and
sentinel Cloud Run Jobs, deploys the dashboard service, creates Cloud Scheduler
triggers, and creates the required service accounts and bucket bindings. It
does not create a webhook secret. Pass `-WebhookSecretName` only when that
Secret Manager secret already exists.

The batch and sentinel jobs mount the `data/` and `reports/` prefixes of the
same Cloud Storage bucket at `/app/data` and `/app/reports`. The dashboard
mounts only the `reports/` prefix read-only, so it consumes published outputs
without write access to the data layer.

The CLI flags follow the current Google Cloud interfaces for [Cloud Run Jobs](https://cloud.google.com/run/docs/create-jobs),
[Cloud Storage volume mounts](https://cloud.google.com/run/docs/configuring/jobs/cloud-storage-volume-mounts),
[Cloud Run services](https://cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts),
and [scheduled Cloud Run Jobs](https://cloud.google.com/run/docs/execute/jobs-on-schedule).

## GitHub Actions deployment

`.github/workflows/deploy-gcp.yml` exposes the same deployment as a manual
production workflow. It uses GitHub OIDC and Workload Identity Federation, so
the repository does not need a long-lived service-account key. Configure these
GitHub environment secrets before running it:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`: the full provider resource name.
- `GCP_DEPLOYER_SERVICE_ACCOUNT`: the service account used by the workflow.

The workflow is manual-only, uses the `production` environment, and grants the
job only `contents: read` and `id-token: write` GitHub permissions. The current
Google GitHub Actions guidance recommends Workload Identity Federation over
service-account key JSON; see the [auth action documentation](https://github.com/google-github-actions/auth)
and [gcloud setup action documentation](https://github.com/google-github-actions/setup-gcloud).

The first successful run produces the latest reports and empty trend report
schemas. Run the pipeline again to create comparable snapshots and populate
the trend reports.

## Artifact contract

| Layer | Local path | Cloud equivalent | Retention purpose |
| --- | --- | --- | --- |
| Raw | `data/raw/**/*.json` | Cloud Storage raw prefix | Immutable source replay |
| Latest processed | `data/processed/**/*.parquet` | BigQuery tables or Storage Parquet | Dashboard and current reports |
| Snapshots | `data/processed_snapshots/**/*.parquet` | Partitioned Storage/BigQuery tables | Historical comparisons |
| Observations | `data/processed/risk_observations_latest.parquet` | BigQuery table or Storage Parquet | Cross-source risk feed |
| Reports | `reports/*.csv` | BigQuery views or generated objects | Dashboard-ready risk outputs |

All scheduled jobs should write a timestamped raw payload and a processed
snapshot before publishing a latest table. A failed run must leave the previous
latest data available and must not overwrite a raw payload.

## GCP deployment plan

The recommended first cloud implementation is:

```text
Cloud Scheduler
  -> Cloud Run Jobs: ingestion + processing + analytics + quality
  -> Cloud Storage: raw JSON, processed Parquet, report CSVs
  -> Cloud Run service: Streamlit dashboard
```

Run the fresh-snapshot sentinel as a separate scheduled job when the batch
cadence is not sufficient:

```text
Cloud Scheduler (short cadence)
  -> Cloud Run Job: python -m src.monitoring.risk_sentinel
  -> JSON webhook and latest sentinel output
```

The sentinel checks current token price changes, protocol TVL changes, and USD
stablecoin peg deviation. It is an early-warning path, not a replacement for
historical scoring or a validated forecast.

For a warehouse-backed phase, load the processed Parquet files into BigQuery
partitioned by ingestion timestamp. Keep the risk SQL in version control and
publish reports only after quality checks pass.

### Required service permissions

The scheduled job service account needs:

- outbound HTTPS access to CoinGecko and DefiLlama;
- `storage.objects.create`, `storage.objects.get`, and
  `storage.objects.list` on the project bucket;
- permission to write logs;
- BigQuery job/table permissions only when the warehouse phase is enabled.

The dashboard service account needs read-only access to the published report
prefix. It does not need write access to raw or processed data.

If webhook alerts are enabled, store `RISK_ALERT_WEBHOOK_URL` as a secret on the
scheduled job. `RISK_ALERT_MIN_SCORE` and `RISK_ALERT_MIN_SCORE_CHANGE` control
the two alert thresholds. The pipeline sends a JSON payload only when the
configured alert selection contains rows. Keep webhook delivery outside the
dashboard service.

No cloud deployment is performed by the local project commands. A GCP project,
region, bucket, and service-account choice must be supplied before provisioning
those external resources.

## Scheduling and failure handling

Run the batch at a cadence appropriate to the source rate limits, starting with
hourly or daily collection. Alert on:

- an ingestion HTTP failure or rate-limit response;
- a zero-row processed table;
- a missing or all-null score column;
- a failed report publish;
- a trend report remaining empty after the second successful snapshot.

The local `src/quality/check_outputs.py` script is the baseline gate for the
same checks in CI and in the scheduled job.

The forecast readiness report is also quality-checked. A forecast with
`insufficient_data` is an expected safe state; a report marked `ready` must
contain forecast rows and temporal validation metrics.

## Streaming phase boundary

Streaming exchange trades, order books, or blockchain events should be added as
a separate ingestion path. They should land in an append-only event topic/table
and feed short-window aggregates; they should not replace the snapshot-based
batch reports until latency and data-quality requirements are proven.
