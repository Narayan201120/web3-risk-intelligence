from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.analytics.stablecoin_depeg_risk_trends import score_snapshot


SNAPSHOT_ROOT = Path("data/processed_snapshots/defillama/stablecoins")
READINESS_OUTPUT_PATH = Path("reports/stablecoin_forecast_readiness.json")
FORECAST_OUTPUT_PATH = Path("reports/stablecoin_forecast_latest.csv")

FORECAST_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "observed_at_utc",
    "depeg_risk_score",
    "forecast_probability",
    "event_horizon_hours",
    "model_type",
]

SCORE_BINS = [-float("inf"), 25.0, 50.0, 70.0, float("inf")]
SCORE_BAND_LABELS = ["normal", "elevated", "high", "critical"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_snapshot_files(snapshot_root: Path = SNAPSHOT_ROOT) -> list[Path]:
    return sorted(snapshot_root.glob("ingestion_date=*/*.parquet"))


def _snapshot_time(frame: pd.DataFrame) -> pd.Timestamp:
    if frame.empty or "ingested_at_utc" not in frame.columns:
        raise ValueError("Stablecoin snapshot is missing ingested_at_utc")
    timestamp = pd.to_datetime(frame["ingested_at_utc"].iloc[0], utc=True)
    if pd.isna(timestamp):
        raise ValueError("Stablecoin snapshot has an invalid ingested_at_utc")
    return timestamp


def _scored_snapshots(snapshot_paths: list[Path]) -> list[tuple[Path, pd.Timestamp, pd.DataFrame]]:
    scored: list[tuple[Path, pd.Timestamp, pd.DataFrame]] = []
    for path in snapshot_paths:
        frame = score_snapshot(path)
        scored.append((path, _snapshot_time(frame), frame))
    return sorted(scored, key=lambda item: item[1])


def build_labeled_dataset(
    snapshot_paths: list[Path],
    *,
    horizon_hours: int = 24,
    event_threshold_pct: float = 1.0,
) -> pd.DataFrame:
    """Build time-safe labels from current features and a later snapshot.

    A row is included only when a future snapshot exists at least
    ``horizon_hours`` after the feature snapshot. The label is whether the
    stablecoin's future USD peg deviation reaches ``event_threshold_pct``.
    """

    scored = _scored_snapshots(snapshot_paths)
    rows: list[pd.DataFrame] = []
    minimum_delta = pd.Timedelta(hours=horizon_hours)

    for index, (_, current_time, current) in enumerate(scored):
        future: pd.DataFrame | None = None
        future_time: pd.Timestamp | None = None
        for _, candidate_time, candidate in scored[index + 1 :]:
            if candidate_time - current_time >= minimum_delta:
                future = candidate
                future_time = candidate_time
                break
        if future is None or future_time is None:
            continue

        current_features = current[
            [
                "id",
                "symbol",
                "name",
                "ingested_at_utc",
                "depeg_risk_score",
                "absolute_depeg",
                "supply_change_1d",
                "supply_change_7d",
                "chain_count",
            ]
        ].copy()
        future_outcome = future[["id", "absolute_depeg"]].rename(
            columns={"absolute_depeg": "future_absolute_depeg"}
        )
        joined = current_features.merge(future_outcome, on="id", how="inner")
        if joined.empty:
            continue

        joined["observed_at_utc"] = pd.to_datetime(
            joined.pop("ingested_at_utc"), utc=True
        ).astype(str)
        joined["future_observed_at_utc"] = future_time.isoformat()
        joined["absolute_depeg_pct"] = joined.pop("absolute_depeg") * 100
        joined["supply_change_1d_pct"] = joined.pop("supply_change_1d") * 100
        joined["supply_change_7d_pct"] = joined.pop("supply_change_7d") * 100
        joined["event_label"] = (
            joined["future_absolute_depeg"] * 100 >= event_threshold_pct
        ).astype("int8")
        rows.append(joined)

    if not rows:
        return pd.DataFrame(
            columns=[
                "id",
                "symbol",
                "name",
                "observed_at_utc",
                "future_observed_at_utc",
                "depeg_risk_score",
                "absolute_depeg_pct",
                "supply_change_1d_pct",
                "supply_change_7d_pct",
                "chain_count",
                "future_absolute_depeg",
                "event_label",
            ]
        )
    return pd.concat(rows, ignore_index=True)


def assess_readiness(
    dataset: pd.DataFrame,
    snapshot_paths: list[Path],
    *,
    minimum_distinct_dates: int = 14,
    minimum_rows: int = 200,
    minimum_positive_events: int = 10,
) -> dict[str, Any]:
    distinct_dates = 0
    if not dataset.empty:
        distinct_dates = pd.to_datetime(
            dataset["observed_at_utc"], utc=True
        ).dt.date.nunique()
    positive_events = (
        int(dataset["event_label"].sum()) if not dataset.empty else 0
    )
    reasons: list[str] = []
    if len(snapshot_paths) < 2:
        reasons.append("at_least_two_snapshots_required")
    if distinct_dates < minimum_distinct_dates:
        reasons.append("more_distinct_observation_dates_required")
    if len(dataset) < minimum_rows:
        reasons.append("more_labeled_rows_required")
    if positive_events < minimum_positive_events:
        reasons.append("more_positive_events_required")

    return {
        "status": "ready" if not reasons else "insufficient_data",
        "snapshot_count": len(snapshot_paths),
        "distinct_observation_dates": distinct_dates,
        "labeled_rows": len(dataset),
        "positive_events": positive_events,
        "reasons": reasons,
    }


def _score_band(scores: pd.Series) -> pd.Series:
    return pd.cut(
        pd.to_numeric(scores, errors="coerce"),
        bins=SCORE_BINS,
        labels=SCORE_BAND_LABELS,
        right=False,
    ).astype("string")


def fit_score_calibration(dataset: pd.DataFrame) -> dict[str, Any]:
    if dataset.empty:
        raise ValueError("Cannot fit calibration on an empty dataset")

    frame = dataset.copy()
    frame["score_band"] = _score_band(frame["depeg_risk_score"])
    global_events = int(frame["event_label"].sum())
    global_rows = len(frame)
    calibration: list[dict[str, Any]] = []
    for band in SCORE_BAND_LABELS:
        band_rows = frame.loc[frame["score_band"] == band]
        rows = len(band_rows)
        events = int(band_rows["event_label"].sum())
        probability = (events + 1) / (rows + 2)
        calibration.append(
            {
                "score_band": band,
                "row_count": rows,
                "event_count": events,
                "probability": round(probability, 8),
            }
        )
    return {
        "model_type": "empirical_risk_score_calibration",
        "global_probability": round(
            (global_events + 1) / (global_rows + 2), 8
        ),
        "calibration": calibration,
    }


def predict_calibrated(
    scores: pd.Series,
    artifact: dict[str, Any],
) -> pd.Series:
    probabilities = {
        row["score_band"]: row["probability"]
        for row in artifact["calibration"]
    }
    bands = _score_band(scores)
    return bands.map(probabilities).fillna(artifact["global_probability"])


def evaluate_forecast(
    actual: pd.Series,
    probabilities: pd.Series,
    *,
    alert_probability: float = 0.5,
) -> dict[str, float]:
    actual_values = pd.to_numeric(actual, errors="coerce").fillna(0).astype(int)
    probability_values = pd.to_numeric(probabilities, errors="coerce").fillna(0)
    predicted = probability_values >= alert_probability
    actual_positive = actual_values == 1
    true_positive = int((predicted & actual_positive).sum())
    false_positive = int((predicted & ~actual_positive).sum())
    false_negative = int((~predicted & actual_positive).sum())
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    brier_score = float(((probability_values - actual_values) ** 2).mean())
    return {
        "brier_score": round(brier_score, 8),
        "precision_at_alert_threshold": round(precision, 8),
        "recall_at_alert_threshold": round(recall, 8),
        "alert_probability_threshold": alert_probability,
    }


def _empty_forecast() -> pd.DataFrame:
    return pd.DataFrame(columns=FORECAST_COLUMNS)


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    frame.to_csv(temporary_path, index=False)
    temporary_path.replace(path)


def run_forecast(
    *,
    snapshot_root: Path = SNAPSHOT_ROOT,
    readiness_output_path: Path = READINESS_OUTPUT_PATH,
    forecast_output_path: Path = FORECAST_OUTPUT_PATH,
    horizon_hours: int = 24,
    event_threshold_pct: float = 1.0,
    minimum_distinct_dates: int = 14,
    minimum_rows: int = 200,
    minimum_positive_events: int = 10,
) -> dict[str, Any]:
    snapshot_paths = get_snapshot_files(snapshot_root)
    dataset = build_labeled_dataset(
        snapshot_paths,
        horizon_hours=horizon_hours,
        event_threshold_pct=event_threshold_pct,
    )
    readiness = assess_readiness(
        dataset,
        snapshot_paths,
        minimum_distinct_dates=minimum_distinct_dates,
        minimum_rows=minimum_rows,
        minimum_positive_events=minimum_positive_events,
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "event_definition": {
            "name": "stablecoin_depeg_event",
            "future_absolute_depeg_at_least_pct": event_threshold_pct,
            "horizon_hours": horizon_hours,
        },
        **readiness,
    }
    forecast = _empty_forecast()

    if readiness["status"] == "ready":
        ordered = dataset.sort_values("observed_at_utc").reset_index(drop=True)
        split_index = int(len(ordered) * 0.7)
        train = ordered.iloc[:split_index]
        test = ordered.iloc[split_index:]
        if train["event_label"].nunique() < 2 or test["event_label"].nunique() < 2:
            report["status"] = "insufficient_data"
            report["reasons"] = ["temporal_holdout_needs_both_event_classes"]
        else:
            validation_artifact = fit_score_calibration(train)
            test_probability = predict_calibrated(
                test["depeg_risk_score"], validation_artifact
            )
            report["model_type"] = validation_artifact["model_type"]
            report["train_rows"] = len(train)
            report["test_rows"] = len(test)
            report["validation_metrics"] = evaluate_forecast(
                test["event_label"], test_probability
            )
            final_artifact = fit_score_calibration(ordered)
            latest_scored = score_snapshot(snapshot_paths[-1])
            forecast = latest_scored[
                ["id", "symbol", "name", "ingested_at_utc", "depeg_risk_score"]
            ].rename(
                columns={
                    "id": "asset_id",
                    "ingested_at_utc": "observed_at_utc",
                }
            )
            forecast["forecast_probability"] = predict_calibrated(
                forecast["depeg_risk_score"], final_artifact
            )
            forecast["event_horizon_hours"] = horizon_hours
            forecast["model_type"] = final_artifact["model_type"]
            forecast = forecast[FORECAST_COLUMNS]
            report["calibration"] = final_artifact["calibration"]
    report["forecast_rows"] = len(forecast)
    _write_json(report, readiness_output_path)
    _write_csv(forecast, forecast_output_path)
    print(f"Stablecoin forecast status: {report['status']}")
    print(f"Saved forecast readiness to {readiness_output_path}")
    print(f"Saved {len(forecast)} forecast rows to {forecast_output_path}")
    return report


def main() -> None:
    run_forecast()


if __name__ == "__main__":
    main()
