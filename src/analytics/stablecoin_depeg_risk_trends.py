from pathlib import Path

import duckdb
import pandas as pd


SNAPSHOT_ROOT = Path("data/processed_snapshots/defillama/stablecoins")
OUTPUT_DIR = Path("reports")
OUTPUT_PATH = OUTPUT_DIR / "stablecoin_depeg_risk_trends.csv"

OUTPUT_COLUMNS = [
    "name_latest",
    "symbol_latest",
    "pegMechanism_latest",
    "depeg_risk_score_previous",
    "depeg_risk_score_latest",
    "risk_score_change",
    "price_previous",
    "price_latest",
    "absolute_depeg_previous",
    "absolute_depeg_latest",
    "circulating_usd_previous",
    "circulating_usd_latest",
    "circulating_change_pct",
    "supply_change_1d_pct_latest",
    "supply_change_7d_pct_latest",
    "chain_count_latest",
    "ingested_at_utc_previous",
    "ingested_at_utc_latest",
]


RISK_QUERY = """
with stablecoin_metrics as (
    select
        id,
        name,
        symbol,
        pegMechanism,
        price,
        circulating_usd,
        circulatingPrevDay_usd,
        circulatingPrevWeek_usd,
        chain_count,
        ingested_at_utc,
        abs(price - 1.0) as absolute_depeg,
        case
            when circulatingPrevDay_usd > 0
                then (circulating_usd - circulatingPrevDay_usd)
                / circulatingPrevDay_usd
            else null
        end as supply_change_1d,
        case
            when circulatingPrevWeek_usd > 0
                then (circulating_usd - circulatingPrevWeek_usd)
                / circulatingPrevWeek_usd
            else null
        end as supply_change_7d
    from read_parquet(?)
    where pegType = 'peggedUSD'
),

scored as (
    select
        *,
        case
            when price is null then 30
            when absolute_depeg >= 0.05 then 40
            when absolute_depeg >= 0.02 then 25
            when absolute_depeg >= 0.01 then 15
            when absolute_depeg >= 0.005 then 8
            else 0
        end
        +
        case
            when supply_change_1d <= -0.20 then 20
            when supply_change_1d <= -0.10 then 12
            when supply_change_1d <= -0.05 then 6
            else 0
        end
        +
        case
            when supply_change_7d <= -0.40 then 20
            when supply_change_7d <= -0.20 then 12
            when supply_change_7d <= -0.10 then 6
            else 0
        end
        +
        case
            when chain_count is null then 5
            when chain_count = 1 then 5
            else 0
        end as depeg_risk_score
    from stablecoin_metrics
)

select
    id,
    name,
    symbol,
    pegMechanism,
    price,
    absolute_depeg,
    circulating_usd,
    supply_change_1d,
    supply_change_7d,
    chain_count,
    depeg_risk_score,
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
            "Stablecoin trend report needs at least two snapshots; "
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
        trend["depeg_risk_score_latest"]
        - trend["depeg_risk_score_previous"]
    )

    trend["circulating_change_pct"] = pd.NA
    valid_previous_supply = trend["circulating_usd_previous"] > 0
    trend.loc[valid_previous_supply, "circulating_change_pct"] = (
        (
            trend.loc[valid_previous_supply, "circulating_usd_latest"]
            - trend.loc[valid_previous_supply, "circulating_usd_previous"]
        )
        / trend.loc[valid_previous_supply, "circulating_usd_previous"]
        * 100
    )

    trend["supply_change_1d_pct_latest"] = (
        trend["supply_change_1d_latest"] * 100
    )
    trend["supply_change_7d_pct_latest"] = (
        trend["supply_change_7d_latest"] * 100
    )

    result = trend[OUTPUT_COLUMNS].sort_values(
        ["risk_score_change", "depeg_risk_score_latest"],
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
