import json

import pandas as pd

from src.monitoring.risk_sentinel import SentinelThresholds
from src.monitoring.risk_sentinel import detect_events
from src.monitoring.risk_sentinel import select_new_events
from src.monitoring.risk_sentinel import write_events


def test_detect_events_captures_market_protocol_and_peg_shocks() -> None:
    events = detect_events(
        [
            {
                "id": "example-token",
                "symbol": "EXT",
                "name": "Example Token",
                "market_cap": 1_000_000,
                "total_volume": 5_000,
                "price_change_percentage_1h_in_currency": -12,
                "price_change_percentage_24h_in_currency": -22,
            }
        ],
        [
            {
                "id": "example-protocol",
                "symbol": "EXP",
                "name": "Example Protocol",
                "change_1h": -7,
                "change_1d": -25,
            }
        ],
        {
            "peggedAssets": [
                {
                    "id": 1,
                    "symbol": "EXD",
                    "name": "Example Dollar",
                    "pegType": "peggedUSD",
                    "price": 0.98,
                }
            ]
        },
        sentinel_run_id="sentinel_test",
        observed_at_utc="2026-09-06T12:00:00Z",
    )

    assert len(events) == 5
    assert set(events["asset_type"]) == {"token", "protocol", "stablecoin"}
    assert set(events.loc[events["asset_type"] == "token", "severity"]) == {
        "critical"
    }
    assert (
        events.loc[events["signal"] == "stablecoin_peg_deviation", "severity"]
        .iloc[0]
        == "critical"
    )


def test_detect_events_respects_custom_thresholds() -> None:
    events = detect_events(
        [
            {
                "id": "quiet-token",
                "symbol": "QTX",
                "name": "Quiet Token",
                "market_cap": 1_000_000,
                "total_volume": 20_000,
                "price_change_percentage_1h_in_currency": -4,
            }
        ],
        [],
        {"peggedAssets": []},
        sentinel_run_id="sentinel_test",
        observed_at_utc="2026-09-06T12:00:00Z",
        thresholds=SentinelThresholds(token_1h_drop_pct=-3),
    )

    assert list(events["signal"]) == ["token_1h_price_shock"]


def test_write_events_replaces_latest_output_atomically(tmp_path) -> None:
    events = pd.DataFrame(
        [
            {
                "event_id": "event-1",
                "sentinel_run_id": "sentinel_test",
                "observed_at_utc": "2026-09-06T12:00:00Z",
                "asset_type": "token",
                "asset_id": "example-token",
                "symbol": "EXT",
                "name": "Example Token",
                "signal": "token_1h_price_shock",
                "severity": "high",
                "value": -7,
                "threshold": -5,
                "details_json": "{}",
            }
        ]
    )
    output_path = tmp_path / "sentinel.json"

    write_events(
        events,
        output_path=output_path,
        sentinel_run_id="sentinel_test",
        observed_at_utc="2026-09-06T12:00:00Z",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["event_count"] == 1
    assert payload["events"][0]["event_id"] == "event-1"
    assert not output_path.with_suffix(".tmp").exists()


def test_select_new_events_deduplicates_persistent_conditions() -> None:
    events = pd.DataFrame(
        [
            {
                "event_id": "token:example:token_1h_price_shock",
                "severity": "high",
            },
            {
                "event_id": "stablecoin:example:stablecoin_peg_deviation",
                "severity": "critical",
            },
        ]
    )

    unchanged = select_new_events(
        events,
        {
            "token:example:token_1h_price_shock": {"severity": "high"},
            "stablecoin:example:stablecoin_peg_deviation": {"severity": "critical"},
        },
    )
    assert unchanged.empty

    escalated = select_new_events(
        events,
        {
            "token:example:token_1h_price_shock": {"severity": "medium"},
            "stablecoin:example:stablecoin_peg_deviation": {
                "severity": "critical"
            },
        },
    )
    assert list(escalated["event_id"]) == ["token:example:token_1h_price_shock"]
