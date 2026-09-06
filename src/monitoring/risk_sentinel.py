from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from src.ingestion.fetch_coingecko_markets import fetch_markets
from src.ingestion.fetch_defillama_protocols import fetch_protocols
from src.ingestion.fetch_defillama_stablecoins import fetch_stablecoins


OUTPUT_PATH = Path("reports/risk_sentinel_latest.json")
STATE_PATH = Path("data/monitoring/risk_sentinel_state.json")

EVENT_COLUMNS = [
    "event_id",
    "sentinel_run_id",
    "observed_at_utc",
    "asset_type",
    "asset_id",
    "symbol",
    "name",
    "signal",
    "severity",
    "value",
    "threshold",
    "details_json",
]


@dataclass(frozen=True)
class SentinelThresholds:
    token_1h_drop_pct: float = -5.0
    token_1h_critical_drop_pct: float = -10.0
    token_24h_drop_pct: float = -10.0
    token_24h_critical_drop_pct: float = -20.0
    protocol_1h_tvl_drop_pct: float = -5.0
    protocol_1d_tvl_drop_pct: float = -10.0
    protocol_1d_critical_drop_pct: float = -20.0
    stablecoin_watch_deviation_pct: float = 0.5
    stablecoin_alert_deviation_pct: float = 1.0
    stablecoin_critical_deviation_pct: float = 2.0


def thresholds_from_environment() -> SentinelThresholds:
    defaults = SentinelThresholds()
    return SentinelThresholds(
        token_1h_drop_pct=float(
            os.getenv("SENTINEL_TOKEN_1H_DROP_PCT", defaults.token_1h_drop_pct)
        ),
        token_1h_critical_drop_pct=float(
            os.getenv(
                "SENTINEL_TOKEN_1H_CRITICAL_DROP_PCT",
                defaults.token_1h_critical_drop_pct,
            )
        ),
        token_24h_drop_pct=float(
            os.getenv("SENTINEL_TOKEN_24H_DROP_PCT", defaults.token_24h_drop_pct)
        ),
        token_24h_critical_drop_pct=float(
            os.getenv(
                "SENTINEL_TOKEN_24H_CRITICAL_DROP_PCT",
                defaults.token_24h_critical_drop_pct,
            )
        ),
        protocol_1h_tvl_drop_pct=float(
            os.getenv(
                "SENTINEL_PROTOCOL_1H_TVL_DROP_PCT",
                defaults.protocol_1h_tvl_drop_pct,
            )
        ),
        protocol_1d_tvl_drop_pct=float(
            os.getenv(
                "SENTINEL_PROTOCOL_1D_TVL_DROP_PCT",
                defaults.protocol_1d_tvl_drop_pct,
            )
        ),
        protocol_1d_critical_drop_pct=float(
            os.getenv(
                "SENTINEL_PROTOCOL_1D_CRITICAL_DROP_PCT",
                defaults.protocol_1d_critical_drop_pct,
            )
        ),
        stablecoin_watch_deviation_pct=float(
            os.getenv(
                "SENTINEL_STABLECOIN_WATCH_DEVIATION_PCT",
                defaults.stablecoin_watch_deviation_pct,
            )
        ),
        stablecoin_alert_deviation_pct=float(
            os.getenv(
                "SENTINEL_STABLECOIN_ALERT_DEVIATION_PCT",
                defaults.stablecoin_alert_deviation_pct,
            )
        ),
        stablecoin_critical_deviation_pct=float(
            os.getenv(
                "SENTINEL_STABLECOIN_CRITICAL_DEVIATION_PCT",
                defaults.stablecoin_critical_deviation_pct,
            )
        ),
    )


def _number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any, fallback: str = "unknown") -> str:
    if value is None or pd.isna(value):
        return fallback
    return str(value)


def _event(
    *,
    sentinel_run_id: str,
    observed_at_utc: str,
    asset_type: str,
    asset_id: Any,
    symbol: Any,
    name: Any,
    signal: str,
    severity: str,
    value: float,
    threshold: float,
    details: dict[str, Any],
) -> dict[str, Any]:
    resolved_asset_id = _text(asset_id)
    event_key = ":".join([asset_type, resolved_asset_id, signal])
    return {
        "event_id": event_key,
        "sentinel_run_id": sentinel_run_id,
        "observed_at_utc": observed_at_utc,
        "asset_type": asset_type,
        "asset_id": resolved_asset_id,
        "symbol": _text(symbol),
        "name": _text(name),
        "signal": signal,
        "severity": severity,
        "value": round(value, 6),
        "threshold": round(threshold, 6),
        "details_json": json.dumps(details, separators=(",", ":")),
    }


def _token_events(
    markets: list[dict[str, Any]],
    *,
    sentinel_run_id: str,
    observed_at_utc: str,
    thresholds: SentinelThresholds,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in markets:
        asset_id = row.get("id")
        symbol = row.get("symbol")
        name = row.get("name")
        change_1h = _number(row.get("price_change_percentage_1h_in_currency"))
        change_24h = _number(
            row.get("price_change_percentage_24h_in_currency")
            if row.get("price_change_percentage_24h_in_currency") is not None
            else row.get("price_change_percentage_24h")
        )

        if change_1h is not None and change_1h <= thresholds.token_1h_drop_pct:
            severity = (
                "critical"
                if change_1h <= thresholds.token_1h_critical_drop_pct
                else "high"
            )
            events.append(
                _event(
                    sentinel_run_id=sentinel_run_id,
                    observed_at_utc=observed_at_utc,
                    asset_type="token",
                    asset_id=asset_id,
                    symbol=symbol,
                    name=name,
                    signal="token_1h_price_shock",
                    severity=severity,
                    value=change_1h,
                    threshold=thresholds.token_1h_drop_pct,
                    details={"price_change_1h_pct": change_1h},
                )
            )

        if change_24h is not None and change_24h <= thresholds.token_24h_drop_pct:
            severity = (
                "critical"
                if change_24h <= thresholds.token_24h_critical_drop_pct
                else "high"
            )
            events.append(
                _event(
                    sentinel_run_id=sentinel_run_id,
                    observed_at_utc=observed_at_utc,
                    asset_type="token",
                    asset_id=asset_id,
                    symbol=symbol,
                    name=name,
                    signal="token_24h_price_shock",
                    severity=severity,
                    value=change_24h,
                    threshold=thresholds.token_24h_drop_pct,
                    details={"price_change_24h_pct": change_24h},
                )
            )

    return events


def _protocol_events(
    protocols: list[dict[str, Any]],
    *,
    sentinel_run_id: str,
    observed_at_utc: str,
    thresholds: SentinelThresholds,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in protocols:
        change_1h = _number(row.get("change_1h"))
        change_1d = _number(row.get("change_1d"))
        asset_id = row.get("id") or row.get("name")

        if change_1h is not None and change_1h <= thresholds.protocol_1h_tvl_drop_pct:
            events.append(
                _event(
                    sentinel_run_id=sentinel_run_id,
                    observed_at_utc=observed_at_utc,
                    asset_type="protocol",
                    asset_id=asset_id,
                    symbol=row.get("symbol"),
                    name=row.get("name"),
                    signal="protocol_1h_tvl_shock",
                    severity="high",
                    value=change_1h,
                    threshold=thresholds.protocol_1h_tvl_drop_pct,
                    details={"tvl_change_1h_pct": change_1h},
                )
            )

        if change_1d is not None and change_1d <= thresholds.protocol_1d_tvl_drop_pct:
            severity = (
                "critical"
                if change_1d <= thresholds.protocol_1d_critical_drop_pct
                else "high"
            )
            events.append(
                _event(
                    sentinel_run_id=sentinel_run_id,
                    observed_at_utc=observed_at_utc,
                    asset_type="protocol",
                    asset_id=asset_id,
                    symbol=row.get("symbol"),
                    name=row.get("name"),
                    signal="protocol_1d_tvl_shock",
                    severity=severity,
                    value=change_1d,
                    threshold=thresholds.protocol_1d_tvl_drop_pct,
                    details={"tvl_change_1d_pct": change_1d},
                )
            )
    return events


def _stablecoin_events(
    payload: dict[str, Any],
    *,
    sentinel_run_id: str,
    observed_at_utc: str,
    thresholds: SentinelThresholds,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in payload.get("peggedAssets", []):
        if row.get("pegType") != "peggedUSD":
            continue
        price = _number(row.get("price"))
        if price is None:
            continue
        deviation_pct = abs(price - 1.0) * 100
        if deviation_pct < thresholds.stablecoin_watch_deviation_pct:
            continue

        if deviation_pct >= thresholds.stablecoin_critical_deviation_pct:
            severity = "critical"
        elif deviation_pct >= thresholds.stablecoin_alert_deviation_pct:
            severity = "high"
        else:
            severity = "medium"

        events.append(
            _event(
                sentinel_run_id=sentinel_run_id,
                observed_at_utc=observed_at_utc,
                asset_type="stablecoin",
                asset_id=row.get("id") or row.get("symbol"),
                symbol=row.get("symbol"),
                name=row.get("name"),
                signal="stablecoin_peg_deviation",
                severity=severity,
                value=deviation_pct,
                threshold=thresholds.stablecoin_watch_deviation_pct,
                details={
                    "price": price,
                    "absolute_deviation_pct": deviation_pct,
                },
            )
        )
    return events


def detect_events(
    markets: list[dict[str, Any]],
    protocols: list[dict[str, Any]],
    stablecoins: dict[str, Any],
    *,
    sentinel_run_id: str,
    observed_at_utc: str,
    thresholds: SentinelThresholds | None = None,
) -> pd.DataFrame:
    resolved_thresholds = thresholds or SentinelThresholds()
    events = [
        *_token_events(
            markets,
            sentinel_run_id=sentinel_run_id,
            observed_at_utc=observed_at_utc,
            thresholds=resolved_thresholds,
        ),
        *_protocol_events(
            protocols,
            sentinel_run_id=sentinel_run_id,
            observed_at_utc=observed_at_utc,
            thresholds=resolved_thresholds,
        ),
        *_stablecoin_events(
            stablecoins,
            sentinel_run_id=sentinel_run_id,
            observed_at_utc=observed_at_utc,
            thresholds=resolved_thresholds,
        ),
    ]
    result = pd.DataFrame(events, columns=EVENT_COLUMNS)
    if not result.empty:
        severity_order = {"critical": 0, "high": 1, "medium": 2}
        result["_severity_order"] = result["severity"].map(severity_order)
        result = result.sort_values(
            ["_severity_order", "asset_type", "asset_id", "signal"]
        ).drop(columns="_severity_order")
        result = result.reset_index(drop=True)
    return result


def write_events(
    events: pd.DataFrame,
    *,
    output_path: Path = OUTPUT_PATH,
    sentinel_run_id: str,
    observed_at_utc: str,
    thresholds: SentinelThresholds | None = None,
) -> Path:
    payload = {
        "schema_version": 1,
        "sentinel_run_id": sentinel_run_id,
        "observed_at_utc": observed_at_utc,
        "event_count": len(events),
        "thresholds": asdict(thresholds or SentinelThresholds()),
        "events": json.loads(events.to_json(orient="records")),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(output_path)
    return output_path


def load_notification_state(state_path: Path = STATE_PATH) -> dict[str, Any]:
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    active_events = payload.get("active_events", {})
    return active_events if isinstance(active_events, dict) else {}


def select_new_events(
    events: pd.DataFrame,
    previous_state: dict[str, Any],
) -> pd.DataFrame:
    if events.empty:
        return events.copy()

    severity_rank = {"critical": 0, "high": 1, "medium": 2}
    selected_indices: list[int] = []
    for index, row in events.iterrows():
        previous = previous_state.get(str(row["event_id"]))
        if not isinstance(previous, dict):
            selected_indices.append(index)
            continue
        current_rank = severity_rank.get(str(row["severity"]), 99)
        previous_rank = severity_rank.get(str(previous.get("severity")), 99)
        if current_rank < previous_rank:
            selected_indices.append(index)
    return events.loc[selected_indices].reset_index(drop=True)


def write_notification_state(
    events: pd.DataFrame,
    state_path: Path = STATE_PATH,
) -> Path:
    active_events = {
        str(row["event_id"]): {
            "severity": str(row["severity"]),
            "observed_at_utc": str(row["observed_at_utc"]),
        }
        for _, row in events.iterrows()
    }
    payload = {"schema_version": 1, "active_events": active_events}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = state_path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(state_path)
    return state_path


def notify_webhook(events: pd.DataFrame, webhook_url: str) -> None:
    if events.empty:
        return
    payload = {
        "event": "web3_risk_sentinel",
        "sentinel_run_id": str(events.iloc[0]["sentinel_run_id"]),
        "observed_at_utc": str(events.iloc[0]["observed_at_utc"]),
        "events": json.loads(events.to_json(orient="records")),
    }
    response = requests.post(webhook_url, json=payload, timeout=15)
    response.raise_for_status()


def run_sentinel(
    *,
    output_path: Path = OUTPUT_PATH,
    state_path: Path = STATE_PATH,
    webhook_url: str | None = None,
    thresholds: SentinelThresholds | None = None,
) -> pd.DataFrame:
    observed_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    sentinel_run_id = f"sentinel_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    resolved_thresholds = thresholds or thresholds_from_environment()
    events = detect_events(
        fetch_markets(page=1, per_page=250),
        fetch_protocols(),
        fetch_stablecoins(),
        sentinel_run_id=sentinel_run_id,
        observed_at_utc=observed_at_utc,
        thresholds=resolved_thresholds,
    )
    write_events(
        events,
        output_path=output_path,
        sentinel_run_id=sentinel_run_id,
        observed_at_utc=observed_at_utc,
        thresholds=resolved_thresholds,
    )

    resolved_webhook = webhook_url or os.getenv("RISK_SENTINEL_WEBHOOK_URL")
    previous_state = load_notification_state(state_path)
    new_events = select_new_events(events, previous_state)
    if resolved_webhook:
        notify_webhook(new_events, resolved_webhook)
    write_notification_state(events, state_path)

    print(f"Detected {len(events)} sentinel events")
    print(f"New or escalated events: {len(new_events)}")
    print(f"Saved sentinel output to {output_path}")
    return events


def main() -> None:
    run_sentinel()


if __name__ == "__main__":
    main()
