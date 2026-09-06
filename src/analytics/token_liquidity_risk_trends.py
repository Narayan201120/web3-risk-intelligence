from pathlib import Path

import duckdb
import pandas as pd


SNAPSHOT_ROOT = Path("data/processed_snapshots/coingecko/markets")
OUTPUT_DIR = Path("reports")
OUTPUT_PATH = OUTPUT_DIR / "token_liquidity_risk_trends.csv"

OUTPUT_COLUMNS = [
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
    return sorted(SNAPSHOT_ROOT.glob("ingestion_date=*/*.parquet"))


def score_snapshot(path: Path) -> pd.DataFrame:
    return duckdb.sql(RISK_QUERY, params=[str(path)]).df()


def write_empty_report() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=OUTPUT_COLUMNS).to_csv(OUTPUT_PATH, index=False)


def main() -> None:
    snapshot_files = get_snapshot_files()

    if len(snapshot_files) < 2:
        write_empty_report()
        print(
            "Token liquidity trend report needs at least two snapshots; "
            f"wrote an empty schema to {OUTPUT_PATH}."
        )
        return

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

    trend["market_cap_change_pct"] = pd.NA
    valid_previous_market_cap = trend["market_cap_previous"] > 0
    trend.loc[valid_previous_market_cap, "market_cap_change_pct"] = (
        (
            trend.loc[valid_previous_market_cap, "market_cap_latest"]
            - trend.loc[valid_previous_market_cap, "market_cap_previous"]
        )
        / trend.loc[valid_previous_market_cap, "market_cap_previous"]
        * 100
    )

    trend["volume_change_pct"] = pd.NA
    valid_previous_volume = trend["total_volume_previous"] > 0
    trend.loc[valid_previous_volume, "volume_change_pct"] = (
        (
            trend.loc[valid_previous_volume, "total_volume_latest"]
            - trend.loc[valid_previous_volume, "total_volume_previous"]
        )
        / trend.loc[valid_previous_volume, "total_volume_previous"]
        * 100
    )

    result = trend[OUTPUT_COLUMNS].sort_values(
        ["risk_score_change", "liquidity_risk_score_latest"],
        ascending=[False, False],
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)

    print(f"Previous snapshot: {previous_path}")
    print(f"Latest snapshot: {latest_path}")
    print(result.head(15).to_string(index=False))
    print(f"\nSaved report to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
