from pathlib import Path
import json
import os

import duckdb
import pandas as pd


PROCESSED_FILES = {
    "markets": Path("data/processed/coingecko/markets_latest.parquet"),
    "protocols": Path("data/processed/defillama/protocols_latest.parquet"),
    "stablecoins": Path("data/processed/defillama/stablecoins_latest.parquet"),
    "risk_observations": Path("data/processed/risk_observations_latest.parquet"),
}

REPORT_FILES = {
    "token_liquidity_risk": Path("reports/token_liquidity_risk_top50.csv"),
    "defi_protocol_risk": Path("reports/defi_protocol_risk_top50.csv"),
    "stablecoin_depeg_risk": Path("reports/stablecoin_depeg_risk_top50.csv"),
    "token_liquidity_risk_trends": Path("reports/token_liquidity_risk_trends.csv"),
    "defi_protocol_risk_trends": Path("reports/defi_protocol_risk_trends.csv"),
    "stablecoin_depeg_risk_trends": Path(
        "reports/stablecoin_depeg_risk_trends.csv"
    ),
    "risk_alerts": Path("reports/risk_alerts_latest.csv"),
}

OBSERVATION_COLUMNS = {
    "pipeline_run_id",
    "observed_at_utc",
    "asset_type",
    "asset_id",
    "symbol",
    "name",
    "source",
    "risk_score_previous",
    "risk_score",
    "risk_score_change",
    "risk_level",
    "risk_factors_json",
}

def assert_file_exists(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing expected file: {path}")
    
def assert_parquet_not_empty(name: str, path: Path) -> None:
    row_count = duckdb.sql(
        "select count(*) as row_count from read_parquet(?)",
        params=[str(path)],
    ).fetchone()[0]
    
    if row_count == 0:
        raise ValueError(f"{name} parquet file is empty: {path}")

    print(f"{name}: {row_count} rows")


def assert_parquet_columns(
    name: str,
    path: Path,
    expected_columns: set[str],
) -> None:
    columns = set(
        duckdb.sql(
            "select * from read_parquet(?) limit 0",
            params=[str(path)],
        ).df().columns
    )
    missing_columns = expected_columns - columns
    if missing_columns:
        raise ValueError(
            f"{name} missing columns: {sorted(missing_columns)}"
        )


def assert_pipeline_manifest_ready() -> None:
    manifest_value = os.getenv("PIPELINE_MANIFEST_PATH")
    run_id = os.getenv("PIPELINE_RUN_ID")
    if not manifest_value or not run_id:
        return

    manifest_path = Path(manifest_value)
    assert_file_exists(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("pipeline_run_id") != run_id:
        raise ValueError("Pipeline manifest run ID does not match the current run")
    if manifest.get("status") != "running":
        raise ValueError("Pipeline manifest is not in the expected running state")

    steps = manifest.get("steps", [])
    previous_steps = steps[:-1] if steps else []
    failed_steps = [
        step["script"]
        for step in previous_steps
        if step.get("status") != "succeeded"
    ]
    if failed_steps:
        raise ValueError(f"Previous pipeline steps failed: {failed_steps}")
    
def assert_report_valid(
    name: str,
    path: Path,
    score_column: str,
    allow_empty: bool = False,
) -> None:
    df = pd.read_csv(path)

    if df.empty and not allow_empty:
        raise ValueError(f"{name} report is empty: {path}")
    
    if score_column not in df.columns:
        raise ValueError(f"{name} missing score column: {score_column}")
    
    if not df.empty and df[score_column].isna().all():
        raise ValueError(f"{name} score column is entirely null: {score_column}")

    suffix = " (waiting for a second snapshot)" if df.empty else ""
    print(f"{name}: {len(df)} rows{suffix}")
    
def main() -> None:
    for name, path in PROCESSED_FILES.items():
        assert_file_exists(path)
        assert_parquet_not_empty(name, path)

    assert_parquet_columns(
        "risk_observations",
        PROCESSED_FILES["risk_observations"],
        OBSERVATION_COLUMNS,
    )
    assert_pipeline_manifest_ready()
    
    report_score_columns = {
        "token_liquidity_risk": "liquidity_risk_score",
        "defi_protocol_risk": "protocol_risk_score",
        "stablecoin_depeg_risk": "depeg_risk_score",
        "token_liquidity_risk_trends": "risk_score_change",
        "defi_protocol_risk_trends": "risk_score_change",
        "stablecoin_depeg_risk_trends": "risk_score_change",
        "risk_alerts": "risk_score",
    }

    for name, path in REPORT_FILES.items():
        assert_file_exists(path)
        assert_report_valid(
            name,
            path,
            report_score_columns[name],
            allow_empty=name.endswith("_trends") or name == "risk_alerts",
        )
    
    print("\nAll quality checks passed.")
    
if __name__ == "__main__":
    main()
