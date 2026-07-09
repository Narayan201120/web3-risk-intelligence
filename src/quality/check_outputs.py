from pathlib import Path

import duckdb
import pandas as pd


PROCESSED_FILES = {
    "markets": Path("data/processed/coingecko/markets_latest.parquet"),
    "protocols": Path("data/processed/defillama/protocols_latest.parquet"),
    "stablecoins": Path("data/processed/defillama/stablecoins_latest.parquet"),
}

REPORT_FILES = {
    "token_liquidity_risk": Path("reports/token_liquidity_risk_top50.csv"),
    "defi_protocol_risk": Path("reports/defi_protocol_risk_top50.csv"),
    "stablecoin_depeg_risk": Path("reports/stablecoin_depeg_risk_top50.csv"),
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
    
def assert_report_valid(name: str, path: Path, score_column: str) -> None:
    df = pd.read_csv(path)
    
    if df.empty:
        raise ValueError(f"{name} report is empty: {path}")
    
    if score_column not in df.columns:
        raise ValueError(f"{name} missing score column: {score_column}")
    
    if df[score_column].isna().all():
        raise ValueError(f"{name} score column is entirely null: {score_column}")
    
    print(f"{name}: {len(df)} rows")
    
def main() -> None:
    for name, path in PROCESSED_FILES.items():
        assert_file_exists(path)
        assert_parquet_not_empty(name, path)
    
    report_score_columns = {
        "token_liquidity_risk": "liquidity_risk_score",
        "defi_protocol_risk": "protocol_risk_score",
        "stablecoin_depeg_risk": "depeg_risk_score",
    }
    
    for name, path in REPORT_FILES.items():
        assert_file_exists(path)
        assert_report_valid(name, path, report_score_columns[name])
    
    print("\nAll quality checks passed.")
    
if __name__ == "__main__":
    main()