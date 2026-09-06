from pathlib import Path
import json
import os

import pandas as pd
import requests


OBSERVATIONS_PATH = Path("data/processed/risk_observations_latest.parquet")
OUTPUT_PATH = Path("reports/risk_alerts_latest.csv")

ALERT_COLUMNS = [
    "alert_id",
    "pipeline_run_id",
    "observed_at_utc",
    "asset_type",
    "asset_id",
    "symbol",
    "name",
    "source",
    "risk_score",
    "risk_score_previous",
    "risk_score_change",
    "risk_level",
    "alert_reason",
    "risk_factors_json",
]


def select_alerts(
    observations: pd.DataFrame,
    minimum_score: float = 50,
    minimum_score_change: float = 10,
) -> pd.DataFrame:
    if observations.empty:
        return pd.DataFrame(columns=ALERT_COLUMNS)

    score = pd.to_numeric(observations["risk_score"], errors="coerce")
    previous = pd.to_numeric(
        observations["risk_score_previous"], errors="coerce"
    )
    change = pd.to_numeric(
        observations["risk_score_change"], errors="coerce"
    )

    high_score = score >= minimum_score
    sharp_increase = change >= minimum_score_change
    candidates = observations.loc[high_score | sharp_increase].copy()
    if candidates.empty:
        return pd.DataFrame(columns=ALERT_COLUMNS)

    candidate_score = pd.to_numeric(candidates["risk_score"], errors="coerce")
    candidate_previous = pd.to_numeric(
        candidates["risk_score_previous"], errors="coerce"
    )
    candidate_change = pd.to_numeric(
        candidates["risk_score_change"], errors="coerce"
    )

    reasons: list[str] = []
    for current_score, prior_score, score_change in zip(
        candidate_score, candidate_previous, candidate_change
    ):
        if pd.notna(score_change) and score_change >= minimum_score_change:
            if pd.notna(current_score) and current_score >= minimum_score:
                reasons.append("risk_increase_and_high_score")
            else:
                reasons.append("risk_increase")
        elif pd.isna(prior_score) and pd.notna(current_score):
            reasons.append("new_high_risk")
        else:
            reasons.append("high_risk")

    candidates["alert_reason"] = reasons
    candidates["alert_id"] = candidates.apply(
        lambda row: ":".join(
            [
                str(row["pipeline_run_id"]),
                str(row["asset_type"]),
                str(row["asset_id"]),
                str(row["alert_reason"]),
            ]
        ),
        axis=1,
    )

    result = candidates[ALERT_COLUMNS].sort_values(
        ["risk_score_change", "risk_score"],
        ascending=[False, False],
        na_position="last",
    )
    return result.reset_index(drop=True)


def notify_webhook(alerts: pd.DataFrame, webhook_url: str) -> None:
    if alerts.empty:
        return

    payload = {
        "event": "web3_risk_alerts",
        "pipeline_run_id": str(alerts.iloc[0]["pipeline_run_id"]),
        "alerts": json.loads(alerts.to_json(orient="records")),
    }
    response = requests.post(webhook_url, json=payload, timeout=15)
    response.raise_for_status()


def emit_alerts(
    observations_path: Path = OBSERVATIONS_PATH,
    output_path: Path = OUTPUT_PATH,
    minimum_score: float = 50,
    minimum_score_change: float = 10,
    webhook_url: str | None = None,
) -> pd.DataFrame:
    if not observations_path.exists():
        raise FileNotFoundError(f"Missing observations: {observations_path}")

    observations = pd.read_parquet(observations_path)
    alerts = select_alerts(
        observations,
        minimum_score=minimum_score,
        minimum_score_change=minimum_score_change,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    alerts.to_csv(output_path, index=False)

    resolved_webhook = webhook_url or os.getenv("RISK_ALERT_WEBHOOK_URL")
    if resolved_webhook:
        notify_webhook(alerts, resolved_webhook)

    print(f"Generated {len(alerts)} risk alerts")
    print(f"Saved alerts to {output_path}")
    if resolved_webhook:
        print("Sent alerts to configured webhook")
    return alerts


def main() -> None:
    emit_alerts(
        minimum_score=float(os.getenv("RISK_ALERT_MIN_SCORE", "50")),
        minimum_score_change=float(
            os.getenv("RISK_ALERT_MIN_SCORE_CHANGE", "10")
        ),
    )


if __name__ == "__main__":
    main()
