# Architecture

This project is structured as a local-first Web3 data platform. The current
version focuses on batch ingestion, analytics-ready storage, risk reporting, and
dashboarding. The design can later move to cloud object storage, a warehouse, and
streaming ingestion without changing the core data flow.

## Current Local Architecture

```text
Public Web3 APIs
  -> Python ingestion scripts
  -> Raw JSON landing zone
  -> Python processing scripts
  -> Processed Parquet latest tables
  -> Processed Parquet historical snapshots
  -> DuckDB analytics reports
  -> Streamlit dashboard
  -> Quality checks
```

## Data Sources

### CoinGecko

Used for token market data:

- Current token price
- Market capitalization
- Trading volume
- 24-hour price movement
- 7-day price movement
- Supply metrics

### DefiLlama Protocols

Used for DeFi protocol health metrics:

- Protocol TVL
- Chain
- Category
- 1-hour TVL change
- 1-day TVL change
- 7-day TVL change
- Audit metadata

### DefiLlama Stablecoins

Used for stablecoin risk monitoring:

- Stablecoin price
- Peg type
- Peg mechanism
- Circulating supply
- Prior day supply
- Prior week supply
- Chain availability

## Storage Layers

### Raw Layer

Raw API responses are stored as JSON under `data/raw/`.

Purpose:

- Preserve source payloads
- Support debugging and replay
- Keep ingestion separate from transformation

### Processed Latest Layer

Latest processed Parquet files are stored under `data/processed/`.

Purpose:

- Provide stable inputs for reports and dashboard
- Keep dashboard reads simple and fast
- Represent the latest available state

### Processed Snapshot Layer

Historical processed Parquet snapshots are stored under
`data/processed_snapshots/`.

Purpose:

- Enable trend analysis
- Compare risk scores across pipeline runs
- Track changes in liquidity, TVL, and depeg risk over time

Example:

```text
data/processed_snapshots/coingecko/markets/ingestion_date=2026-07-09/
  markets_20260709T134358Z.parquet
```

## Analytics Layer

DuckDB reads the processed Parquet datasets and generates CSV reports under
`reports/`.

Current reports:

- `token_liquidity_risk_top50.csv`
- `token_liquidity_risk_trends.csv`
- `defi_protocol_risk_top50.csv`
- `stablecoin_depeg_risk_top50.csv`

## Dashboard Layer

The Streamlit dashboard reads generated CSV reports and exposes:

- Token liquidity risk rankings
- Token liquidity risk trends
- DeFi protocol risk rankings
- Stablecoin depeg risk rankings

## Quality Layer

The quality check script validates that:

- Expected processed Parquet files exist
- Processed tables are not empty
- Expected report files exist
- Report score columns exist
- Report score columns are not fully null

## Current Pipeline Orchestration

The full local pipeline is run by:

```powershell
python src\run_pipeline.py
```

The runner executes ingestion, processing, analytics, and quality checks in a
fixed order. If any step fails, the pipeline stops.

## Future Cloud Architecture

The local architecture maps cleanly to a cloud deployment.

```text
Public APIs
  -> Cloud scheduled jobs
  -> Object storage raw zone
  -> Object storage processed zone
  -> Warehouse external or loaded tables
  -> SQL analytics models
  -> Dashboard
  -> Data quality checks
```

Example GCP mapping:

```text
Cloud Scheduler
  -> Cloud Run ingestion jobs
  -> Cloud Storage raw JSON
  -> Cloud Storage processed Parquet
  -> BigQuery external tables or loaded tables
  -> BigQuery SQL analytics
  -> Streamlit/Cloud Run dashboard
```

## Future Streaming Architecture

The streaming phase can add exchange trades, order book updates, or on-chain
events.

```text
Exchange WebSocket / Blockchain RPC
  -> Streaming producer
  -> Pub/Sub or Kafka
  -> Stream processor
  -> Streaming raw event table
  -> Aggregated risk metrics
  -> Real-time dashboard
```

Initial streaming use cases:

- Live token volume spike detection
- Stablecoin depeg alerts
- Large transfer monitoring
- DEX swap anomaly detection
- Protocol TVL shock monitoring

## Design Principles

- Keep raw data immutable
- Separate ingestion, processing, analytics, dashboard, and quality checks
- Use Parquet for efficient local analytics
- Keep latest files for simple dashboard reads
- Keep snapshots for historical trend analysis
- Make every generated output reproducible from source scripts
