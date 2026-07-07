from pathlib import Path

import duckdb


INPUT_PATH = Path("data/processed/defillama/protocols_latest.parquet")
OUTPUT_DIR = Path("reports")


QUERY = """
with protocol_metrics as (
    select
        id,
        name,
        symbol,
        chain,
        category,
        tvl,
        change_1h,
        change_1d,
        change_7d,
        mcap,
        audits,
        url,
        case
            when mcap > 0 then tvl / mcap
            else null
        end as tvl_to_mcap_ratio
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
    name,
    symbol,
    chain,
    category,
    round(tvl, 2) as tvl,
    round(change_1d, 2) as change_1d,
    round(change_7d, 2) as change_7d,
    audits,
    round(tvl_to_mcap_ratio, 4) as tvl_to_mcap_ratio,
    protocol_risk_score,
    url
from scored
where tvl is not null
order by protocol_risk_score desc, tvl desc
limit 50
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = duckdb.sql(QUERY, params=[str(INPUT_PATH)]).df()

    output_path = OUTPUT_DIR / "defi_protocol_risk_top50.csv"
    result.to_csv(output_path, index=False)

    print(result.head(15).to_string(index=False))
    print(f"\nSaved report to {output_path}")


if __name__ == "__main__":
    main()