from pathlib import Path

import duckdb


INPUT_PATH = Path("data/processed/defillama/stablecoins_latest.parquet")
OUTPUT_DIR = Path("reports")


QUERY = """
with stablecoin_metrics as (
    select
        id,
        name,
        symbol,
        gecko_id,
        pegType,
        pegMechanism,
        price,
        circulating_usd,
        circulatingPrevDay_usd,
        circulatingPrevWeek_usd,
        circulatingPrevMonth_usd,
        chain_count,
        abs(price - 1.0) as absolute_depeg,
        case
            when circulatingPrevDay_usd > 0
                then (circulating_usd - circulatingPrevDay_usd) /
                circulatingPrevDay_usd
            else null
        end as supply_change_1d,
        case
            when circulatingPrevWeek_usd > 0
                then (circulating_usd - circulatingPrevWeek_usd) /
                circulatingPrevWeek_usd
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
    name,
    symbol,
    pegMechanism,
    price,
    round(absolute_depeg, 6) as absolute_depeg,
    round(circulating_usd, 2) as circulating_usd,
    round(supply_change_1d * 100, 2) as supply_change_1d_pct,
    round(supply_change_7d * 100, 2) as supply_change_7d_pct,
    chain_count,
    depeg_risk_score
from scored
where circulating_usd is not null
order by depeg_risk_score desc, circulating_usd desc
limit 50
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = duckdb.sql(QUERY, params=[str(INPUT_PATH)]).df()

    output_path = OUTPUT_DIR / "stablecoin_depeg_risk_top50.csv"
    result.to_csv(output_path, index=False)

    print(result.head(15).to_string(index=False))
    print(f"\nSaved report to {output_path}")


if __name__ == "__main__":
    main()