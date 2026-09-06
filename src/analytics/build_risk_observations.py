from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pandas as pd


REPORTS_DIR = Path("reports")
OUTPUT_PATH = Path("data/processed/risk_observations_latest.parquet")
SNAPSHOT_ROOT = Path("data/processed_snapshots/risk_observations")

OUTPUT_COLUMNS = [
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
]

REPORT_SPECS = [
    {
        "asset_type": "token",
        "source": "coingecko",
        "current_file": "token_liquidity_risk_top50.csv",
        "trend_file": "token_liquidity_risk_trends.csv",
        "id_column": "id",
        "symbol_column": "symbol",
        "name_column": "name",
        "score_column": "liquidity_risk_score",
        "trend_symbol_column": "symbol_latest",
        "trend_name_column": "name_latest",
        "trend_previous_column": "liquidity_risk_score_previous",
        "trend_change_column": "risk_score_change",
    },
    {
        "asset_type": "protocol",
        "source": "defillama",
        "current_file": "defi_protocol_risk_top50.csv",
        "trend_file": "defi_protocol_risk_trends.csv",
        "id_column": None,
        "symbol_column": "symbol",
        "name_column": "name",
        "score_column": "protocol_risk_score",
        "trend_symbol_column": "symbol_latest",
        "trend_name_column": "name_latest",
        "trend_previous_column": "protocol_risk_score_previous",
        "trend_change_column": "risk_score_change",
    },
    {
        "asset_type": "stablecoin",
        "source": "defillama",
        "current_file": "stablecoin_depeg_risk_top50.csv",
        "trend_file": "stablecoin_depeg_risk_trends.csv",
        "id_column": None,
        "symbol_column": "symbol",
        "name_column": "name",
        "score_column": "depeg_risk_score",
        "trend_symbol_column": "symbol_latest",
        "trend_name_column": "name_latest",
        "trend_previous_column": "depeg_risk_score_previous",
        "trend_change_column": "risk_score_change",
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_context(
    run_id: str | None = None,
    observed_at_utc: str | None = None,
) -> tuple[str, str]:
    resolved_run_id = run_id or os.getenv("PIPELINE_RUN_ID")
    if not resolved_run_id:
        resolved_run_id = f"manual_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"

    resolved_observed_at = (
        observed_at_utc
        or os.getenv("PIPELINE_STARTED_AT_UTC")
        or _utc_now()
    )
    return resolved_run_id, resolved_observed_at


def _join_key(symbol: object, name: object) -> str:
    normalized_symbol = str(symbol if pd.notna(symbol) else "").strip().lower()
    normalized_name = str(name if pd.notna(name) else "").strip().lower()
    return f"{normalized_symbol}|{normalized_name}"


def _number(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _risk_level(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 70:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "elevated"
    return "normal"


def _risk_factors(asset_type: str, row: pd.Series) -> list[str]:
    factors: list[str] = []

    if asset_type == "token":
        volume_ratio = _number(row.get("volume_to_market_cap_ratio"))
        drawdown_24h = _number(row.get("price_change_percentage_24h"))
        drawdown_7d = _number(row.get("price_change_percentage_7d"))
        supply_ratio = _number(row.get("circulating_supply_ratio"))

        if volume_ratio is None or volume_ratio < 0.01:
            factors.append("thin_volume")
        elif volume_ratio < 0.03:
            factors.append("soft_volume")
        if drawdown_24h is not None and drawdown_24h <= -5:
            factors.append("24h_drawdown")
        if drawdown_7d is not None and drawdown_7d <= -10:
            factors.append("7d_drawdown")
        if supply_ratio is None or supply_ratio < 0.25:
            factors.append("incomplete_supply")

    elif asset_type == "protocol":
        tvl = _number(row.get("tvl"))
        change_1d = _number(row.get("change_1d"))
        change_7d = _number(row.get("change_7d"))
        audits = _number(row.get("audits"))

        if tvl is None or tvl <= 0:
            factors.append("zero_tvl")
        elif tvl < 1_000_000:
            factors.append("small_tvl")
        if change_1d is not None and change_1d <= -5:
            factors.append("1d_tvl_drawdown")
        if change_7d is not None and change_7d <= -10:
            factors.append("7d_tvl_drawdown")
        if audits is None or audits == 0:
            factors.append("missing_audit_signal")

    else:
        absolute_depeg = _number(row.get("absolute_depeg"))
        supply_1d = _number(row.get("supply_change_1d_pct"))
        supply_7d = _number(row.get("supply_change_7d_pct"))
        chain_count = _number(row.get("chain_count"))

        if absolute_depeg is None:
            factors.append("missing_price")
        elif absolute_depeg >= 0.01:
            factors.append("peg_deviation")
        if supply_1d is not None and supply_1d <= -5:
            factors.append("1d_supply_contraction")
        if supply_7d is not None and supply_7d <= -10:
            factors.append("7d_supply_contraction")
        if chain_count is None or chain_count <= 1:
            factors.append("limited_chain_breadth")

    return factors


def _load_report(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing risk report: {path}")
    return pd.read_csv(path)


def build_observations(
    reports_dir: Path = REPORTS_DIR,
    output_path: Path = OUTPUT_PATH,
    snapshot_root: Path = SNAPSHOT_ROOT,
    run_id: str | None = None,
    observed_at_utc: str | None = None,
) -> pd.DataFrame:
    resolved_run_id, resolved_observed_at = _run_context(run_id, observed_at_utc)
    rows: list[dict[str, object]] = []

    for spec in REPORT_SPECS:
        current = _load_report(reports_dir / spec["current_file"])
        trend = _load_report(reports_dir / spec["trend_file"])

        trend_lookup = {
            _join_key(row[spec["trend_symbol_column"]], row[spec["trend_name_column"]]): row
            for _, row in trend.iterrows()
        }

        for _, row in current.iterrows():
            symbol = row.get(spec["symbol_column"])
            name = row.get(spec["name_column"])
            trend_row = trend_lookup.get(_join_key(symbol, name), {})
            score = _number(row.get(spec["score_column"]))
            previous_score = _number(
                trend_row.get(spec["trend_previous_column"])
                if isinstance(trend_row, pd.Series)
                else None
            )
            score_change = _number(
                trend_row.get(spec["trend_change_column"])
                if isinstance(trend_row, pd.Series)
                else None
            )
            raw_asset_id = (
                row.get(spec["id_column"])
                if spec["id_column"]
                else _join_key(symbol, name)
            )

            rows.append(
                {
                    "pipeline_run_id": resolved_run_id,
                    "observed_at_utc": resolved_observed_at,
                    "asset_type": spec["asset_type"],
                    "asset_id": str(raw_asset_id),
                    "symbol": str(symbol),
                    "name": str(name),
                    "source": spec["source"],
                    "risk_score_previous": previous_score,
                    "risk_score": score,
                    "risk_score_change": score_change,
                    "risk_level": _risk_level(score),
                    "risk_factors_json": json.dumps(
                        _risk_factors(spec["asset_type"], row),
                        separators=(",", ":"),
                    ),
                }
            )

    observations = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if observations.empty:
        raise ValueError("Risk observation build produced no rows")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    observations.to_parquet(output_path, index=False)

    observed_date = pd.Timestamp(resolved_observed_at).strftime("%Y-%m-%d")
    snapshot_dir = snapshot_root / f"ingestion_date={observed_date}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"risk_observations_{resolved_run_id}.parquet"
    observations.to_parquet(snapshot_path, index=False)

    print(f"Built {len(observations)} risk observations")
    print(f"Saved latest observations to {output_path}")
    print(f"Saved observation snapshot to {snapshot_path}")
    return observations


def main() -> None:
    build_observations()


if __name__ == "__main__":
    main()
