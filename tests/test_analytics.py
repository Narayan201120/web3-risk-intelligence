from pathlib import Path

import pandas as pd
import pytest

from src.analytics import build_risk_observations
from src.analytics import defi_protocol_risk_trends
from src.analytics import stablecoin_depeg_risk_trends
from src.analytics import token_liquidity_risk_trends
from src.alerts.emit_risk_alerts import select_alerts


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


def test_build_observations_joins_trends_and_records_factors(tmp_path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    pd.DataFrame(
        [
            {
                "market_cap_rank": 1,
                "id": "example-token",
                "symbol": "EXT",
                "name": "Example Token",
                "market_cap": 1_000_000,
                "total_volume": 5_000,
                "volume_to_market_cap_ratio": 0.005,
                "price_change_percentage_24h": -12,
                "price_change_percentage_7d": -22,
                "circulating_supply_ratio": 0.2,
                "liquidity_risk_score": 65,
            }
        ]
    ).to_csv(reports_dir / "token_liquidity_risk_top50.csv", index=False)
    pd.DataFrame(
        [
            {
                "symbol_latest": "EXT",
                "name_latest": "Example Token",
                "liquidity_risk_score_previous": 40,
                "liquidity_risk_score_latest": 65,
                "risk_score_change": 25,
            }
        ]
    ).to_csv(reports_dir / "token_liquidity_risk_trends.csv", index=False)

    pd.DataFrame(
        [
            {
                "name": "Example Protocol",
                "symbol": "EXP",
                "tvl": 100_000,
                "change_1d": -12,
                "change_7d": -25,
                "audits": 0,
                "protocol_risk_score": 70,
            }
        ]
    ).to_csv(reports_dir / "defi_protocol_risk_top50.csv", index=False)
    pd.DataFrame(
        [
            {
                "symbol_latest": "EXP",
                "name_latest": "Example Protocol",
                "protocol_risk_score_previous": 30,
                "protocol_risk_score_latest": 70,
                "risk_score_change": 40,
            }
        ]
    ).to_csv(reports_dir / "defi_protocol_risk_trends.csv", index=False)

    pd.DataFrame(
        [
            {
                "name": "Example Dollar",
                "symbol": "EXD",
                "pegMechanism": "fiat-backed",
                "price": 0.96,
                "absolute_depeg": 0.04,
                "circulating_usd": 800,
                "supply_change_1d_pct": -20,
                "supply_change_7d_pct": -20,
                "chain_count": 1,
                "depeg_risk_score": 62,
            }
        ]
    ).to_csv(reports_dir / "stablecoin_depeg_risk_top50.csv", index=False)
    pd.DataFrame(
        [
            {
                "symbol_latest": "EXD",
                "name_latest": "Example Dollar",
                "depeg_risk_score_previous": 10,
                "depeg_risk_score_latest": 62,
                "risk_score_change": 52,
            }
        ]
    ).to_csv(reports_dir / "stablecoin_depeg_risk_trends.csv", index=False)

    observations = build_risk_observations.build_observations(
        reports_dir=reports_dir,
        output_path=tmp_path / "processed" / "risk_observations_latest.parquet",
        snapshot_root=tmp_path / "snapshots",
        run_id="run_test",
        observed_at_utc="2026-09-06T12:00:00Z",
    )

    assert len(observations) == 3
    token = observations.loc[observations["asset_type"] == "token"].iloc[0]
    assert token["risk_score_change"] == 25
    assert token["risk_level"] == "high"
    assert "thin_volume" in token["risk_factors_json"]
    assert (tmp_path / "processed" / "risk_observations_latest.parquet").exists()

    alerts = select_alerts(observations, minimum_score=50, minimum_score_change=10)
    assert len(alerts) == 3
    assert set(alerts["alert_reason"]) == {"risk_increase_and_high_score"}
