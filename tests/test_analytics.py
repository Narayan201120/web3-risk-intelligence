from pathlib import Path

import pandas as pd
import pytest

from src.analytics import defi_protocol_risk_trends
from src.analytics import stablecoin_depeg_risk_trends
from src.analytics import token_liquidity_risk_trends


def _create_snapshot(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"placeholder": [1]}).to_parquet(path, index=False)


def test_first_run_trend_reports_are_schema_valid(tmp_path, monkeypatch) -> None:
    modules_and_names = [
        (token_liquidity_risk_trends, "token_liquidity_risk_trends.csv"),
        (defi_protocol_risk_trends, "defi_protocol_risk_trends.csv"),
        (stablecoin_depeg_risk_trends, "stablecoin_depeg_risk_trends.csv"),
    ]

    for module, filename in modules_and_names:
        snapshot_root = tmp_path / module.__name__.split(".")[-1]
        output_dir = tmp_path / "reports"
        _create_snapshot(snapshot_root / "ingestion_date=2026-07-13" / "one.parquet")

        monkeypatch.setattr(module, "SNAPSHOT_ROOT", snapshot_root)
        monkeypatch.setattr(module, "OUTPUT_DIR", output_dir)
        monkeypatch.setattr(module, "OUTPUT_PATH", output_dir / filename)

        module.main()

        result = pd.read_csv(output_dir / filename)
        assert result.empty
        assert "risk_score_change" in result.columns


def test_stablecoin_score_snapshot_calculates_depeg_signal(tmp_path) -> None:
    path = tmp_path / "stablecoins.parquet"
    pd.DataFrame(
        {
            "id": [1],
            "name": ["Example Dollar"],
            "symbol": ["EXD"],
            "pegType": ["peggedUSD"],
            "pegMechanism": ["fiat-backed"],
            "price": [0.96],
            "circulating_usd": [800.0],
            "circulatingPrevDay_usd": [1_000.0],
            "circulatingPrevWeek_usd": [1_000.0],
            "chain_count": [1],
            "ingested_at_utc": ["20260713T145111Z"],
        }
    ).to_parquet(path, index=False)

    result = stablecoin_depeg_risk_trends.score_snapshot(path)

    assert result.loc[0, "absolute_depeg"] == pytest.approx(0.04)
    assert result.loc[0, "depeg_risk_score"] == 62
