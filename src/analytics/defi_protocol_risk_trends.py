from pathlib import Path

import duckdb
import pandas as pd

SNAPSHOT_ROOT = Path("data/processed_snapshots/defillama/protocols")
OUTPUT_DIR = Path("reports")

RISK_QUERY = """
with protocol_metrics as (
    select
        id,
        name,
        symbol,
        chain,
        category,
        tvl,
        change_1d,
        change_7d,
        audits,
        ingested_at_utc
    from read_parquet(?)
),

scored as (
    select
        *,
        case
            when tvl is null or tvl <= 0 then 25
            when tvl < 1000000 then 20
            when tvl < 10000000 then 10
            else 0
        end
        +
        case
            when change_1d <= -20 then 25
            when change_1d <= -10 then 15
            when change_1d <= -5 then 8
            else 0
        end
        +
        case
            when change_7d <= -40 then 25
            when change_7d <= -20 then 15
            when change_7d <= -10 then 8
            else 0
        end
        +
        case
            when audits is null then 10
            when audits = 0 then 10
            else 0
        end as protocol_risk_score
    from protocol_metrics
)

select
    id,
    name,
    symbol,
    chain,
    category,
    tvl,
    change_1d,
    change_7d,
    audits,
    protocol_risk_score,
    ingested_at_utc
from scored
"""

def get_snapshot_files() -> list[Path]:
    files = sorted(SNAPSHOT_ROOT.glob("ingestion_date=*/*.parquet"))
    if len(files) < 2:
        raise ValueError(
            "Need at least two DeFiLlama protocol snapshots to calculate trends. "
            "Run the pipeline at least twice. "
        )
    return files

def score_snapshot(path: Path) -> pd.DataFrame:
    return duckdb.sql(RISK_QUERY, params=[str(path)]).df()

def main() -> None:
    snapshot_files = get_snapshot_files()
    previous_path = snapshot_files[-2]
    latest_path = snapshot_files[-1]
    
    previous = score_snapshot(previous_path)
    latest = score_snapshot(latest_path)
    
    trend = latest.merge(
        previous,
        on = "id",
        suffixes=("_latest", "_previous"),
    )
    
    trend["risk_score_change"] = (
        trend["protocol_risk_score_latest"] - trend["protocol_risk_score_previous"]
    )
    
    trend["tvl_change_pct"] = None
    valid_previous_tvl = trend["tvl_previous"] > 0

    trend.loc[valid_previous_tvl, "tvl_change_pct"] = (
        (trend.loc[valid_previous_tvl, "tvl_latest"]
        - trend.loc[valid_previous_tvl, "tvl_previous"])
        / trend.loc[valid_previous_tvl, "tvl_previous"]
        * 100
    )
    
    columns = [
            "name_latest",
            "symbol_latest",
            "chain_latest",
            "category_latest",
            "protocol_risk_score_previous",
            "protocol_risk_score_latest",
            "risk_score_change",
            "tvl_previous",
            "tvl_latest",
            "tvl_change_pct",
            "change_1d_latest",
            "change_7d_latest",
            "audits_latest",
            "ingested_at_utc_previous",
            "ingested_at_utc_latest",
        ]

    result = trend[columns].sort_values(
        ["risk_score_change", "protocol_risk_score_latest"],
        ascending=[False, False],
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "defi_protocol_risk_trends.csv"
    result.to_csv(output_path, index=False)

    print(f"Previous snapshot: {previous_path}")
    print(f"Latest snapshot: {latest_path}")
    print(result.head(15).to_string(index=False))
    print(f"\nSaved report to {output_path}")


if __name__ == "__main__":
    main()