from pathlib import Path

import pandas as pd

from src.forecasting.stablecoin_forecast import assess_readiness
from src.forecasting.stablecoin_forecast import evaluate_forecast
from src.forecasting.stablecoin_forecast import fit_score_calibration
from src.forecasting.stablecoin_forecast import predict_calibrated


def _dataset() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "depeg_risk_score": [5, 20, 30, 55, 75, 80],
            "event_label": [0, 0, 1, 0, 1, 1],
            "observed_at_utc": pd.date_range(
                "2026-01-01", periods=6, freq="D", tz="UTC"
            ).astype(str),
        }
    )


def test_score_calibration_produces_probabilities_by_risk_band() -> None:
    dataset = _dataset()
    artifact = fit_score_calibration(dataset)

    probabilities = predict_calibrated(dataset["depeg_risk_score"], artifact)

    assert artifact["model_type"] == "empirical_risk_score_calibration"
    assert probabilities.iloc[0] < probabilities.iloc[-1]
    assert all(0 <= probability <= 1 for probability in probabilities)


def test_forecast_metrics_are_calculated_from_future_labels() -> None:
    metrics = evaluate_forecast(
        pd.Series([0, 1, 1, 0]),
        pd.Series([0.1, 0.8, 0.7, 0.2]),
    )

    assert metrics["brier_score"] < 0.1
    assert metrics["precision_at_alert_threshold"] == 1.0
    assert metrics["recall_at_alert_threshold"] == 1.0


def test_readiness_blocks_short_history() -> None:
    report = assess_readiness(
        _dataset(),
        [Path("one.parquet"), Path("two.parquet")],
        minimum_distinct_dates=14,
        minimum_rows=200,
        minimum_positive_events=10,
    )

    assert report["status"] == "insufficient_data"
    assert "more_distinct_observation_dates_required" in report["reasons"]
