from pathlib import Path

import duckdb
import pandas as pd


SNAPSHOT_ROOT = Path("data/processed_snapshots/coingecko/markets")
OUTPUT_DIR = Path("reports")


RISK_QUERY = """
with token_metrics as (
    select
        id,
        symbol,
        name,
        market_cap,
        total_volume,
        price_change_percentage_24h,
        price_change_percentage_7d_in_currency,
        circulating_supply,
        total_supply,
        ingested_at_utc,
        case
            when market_cap > 0 then total_volume / market_cap
            else null
        end as volume_to_market_cap_ratio,
        case
            when circulating_supply > 0 and total_supply > 0
                then circulating_supply / total_supply
            else null
        end as circulating_supply_ratio
    from read_parquet(?)
),

scored as (
    select
        *,
        case
            when volume_to_market_cap_ratio is null then 25
            when volume_to_market_cap_ratio < 0.01 then 25
            when volume_to_market_cap_ratio < 0.03 then 15
            when volume_to_market_cap_ratio < 0.05 then 8
            else 0
        end
        +
        case
            when price_change_percentage_24h <= -10 then 20
            when price_change_percentage_24h <= -5 then 10
            else 0
        end
        +
        case
            when price_change_percentage_7d_in_currency <= -20 then 20
            when price_change_percentage_7d_in_currency <= -10 then 10
            else 0
        end
        +
        case
            when circulating_supply_ratio is null then 10
            when circulating_supply_ratio < 0.25 then 10
            else 0
        end as liquidity_risk_score
    from token_metrics
)

select
    id,
    symbol,
    name,
    market_cap,
    total_volume,
    round(volume_to_market_cap_ratio, 4) as volume_to_market_cap_ratio,
    liquidity_risk_score,
    ingested_at_utc
from scored
"""


def get_snapshot_files() -> list[Path]:
    files = sorted(SNAPSHOT_ROOT.glob("ingestion_date=*/*.parquet"))
    if len(files) < 2:
        raise ValueError(
            "Need at least two CoinGecko market snapshots to calculate trends. "
            "Run the pipeline at least twice."
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
        on="id",
        suffixes=("_latest", "_previous"),
    )

    trend["risk_score_change"] = (
        trend["liquidity_risk_score_latest"]
        - trend["liquidity_risk_score_previous"]
    )

    trend["market_cap_change_pct"] = (
        (trend["market_cap_latest"] - trend["market_cap_previous"])
        / trend["market_cap_previous"]
        * 100
    )

    trend["volume_change_pct"] = (
        (trend["total_volume_latest"] - trend["total_volume_previous"])
        / trend["total_volume_previous"]
        * 100
    )

    columns = [
        "symbol_latest",
        "name_latest",
        "liquidity_risk_score_previous",
        "liquidity_risk_score_latest",
        "risk_score_change",
        "market_cap_change_pct",
        "volume_change_pct",
        "volume_to_market_cap_ratio_previous",
        "volume_to_market_cap_ratio_latest",
        "ingested_at_utc_previous",
        "ingested_at_utc_latest",
    ]

    result = trend[columns].sort_values(
        ["risk_score_change", "liquidity_risk_score_latest"],
        ascending=[False, False],
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "token_liquidity_risk_trends.csv"
    result.to_csv(output_path, index=False)

    print(f"Previous snapshot: {previous_path}")
    print(f"Latest snapshot: {latest_path}")
    print(result.head(15).to_string(index=False))
    print(f"\nSaved report to {output_path}")


if __name__ == "__main__":
    main()
