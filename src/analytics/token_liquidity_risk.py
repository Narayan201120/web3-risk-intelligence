from pathlib import Path
import duckdb

INPUT_PATH = Path("data/processed/coingecko/markets_latest.parquet")
OUTPUT_DIR = Path("reports")


QUERY = """
with token_metrics as (
    select
        id,
        symbol,
        name,
        current_price,
        market_cap,
        market_cap_rank,
        total_volume,
        price_change_percentage_24h,
        price_change_percentage_7d_in_currency,
        circulating_supply,
        total_supply,
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
    market_cap_rank,
    id,
    symbol,
    name,
    current_price,
    market_cap,
    total_volume,
    round(volume_to_market_cap_ratio, 4) as volume_to_market_cap_ratio,
    round(price_change_percentage_24h, 2) as price_change_percentage_24h,
    round(price_change_percentage_7d_in_currency, 2) as price_change_percentage_7d,
    round(circulating_supply_ratio, 4) as circulating_supply_ratio,
    liquidity_risk_score
from scored
where market_cap is not null
order by liquidity_risk_score desc, market_cap desc
limit 50
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = duckdb.sql(QUERY, params=[str(INPUT_PATH)]).df()

    output_path = OUTPUT_DIR / "token_liquidity_risk_top50.csv"
    result.to_csv(output_path, index=False)

    print(result.head(15).to_string(index=False))
    print(f"\nSaved report to {output_path}")


if __name__ == "__main__":
    main()