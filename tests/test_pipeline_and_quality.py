import pandas as pd

from src import run_pipeline
from src.quality.check_outputs import assert_report_valid


def test_pipeline_includes_stablecoin_trends_before_quality_checks() -> None:
    trend_step = "src/analytics/stablecoin_depeg_risk_trends.py"
    observation_step = "src/analytics/build_risk_observations.py"
    alert_step = "src/alerts/emit_risk_alerts.py"

    assert trend_step in run_pipeline.STEPS
    assert observation_step in run_pipeline.STEPS
    assert alert_step in run_pipeline.STEPS
    assert run_pipeline.STEPS.index(observation_step) < run_pipeline.STEPS.index(
        alert_step
    )
    assert run_pipeline.STEPS.index(trend_step) < run_pipeline.STEPS.index(
        "src/quality/check_outputs.py"
    )


def test_quality_accepts_empty_trend_report_with_schema(tmp_path) -> None:
    path = tmp_path / "trend.csv"
    pd.DataFrame(columns=["risk_score_change"]).to_csv(path, index=False)

    assert_report_valid(
        "stablecoin_depeg_risk_trends",
        path,
        "risk_score_change",
        allow_empty=True,
    )
