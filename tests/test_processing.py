import pandas as pd

from src.processing.process_coingecko_markets import normalize_markets
from src.processing.process_defillama_protocols import normalize_protocols
from src.processing.process_defillama_stablecoins import normalize_stablecoins


def test_normalize_markets_keeps_numeric_metrics_numeric() -> None:
    payload = {
        "ingested_at_utc": "20260713T145106Z",
        "source": "coingecko",
        "data": [
            {
                "id": "example-token",
                "symbol": "ext",
                "name": "Example Token",
                "current_price": "1.25",
                "market_cap": "1000000",
                "market_cap_rank": 42,
                "total_volume": 25000,
                "price_change_percentage_24h": -6.5,
                "price_change_percentage_7d_in_currency": -12.0,
                "circulating_supply": 500000,
                "total_supply": 1000000,
            }
        ],
    }

    result = normalize_markets(payload)

    assert result.loc[0, "current_price"] == 1.25
    assert result.loc[0, "market_cap"] == 1_000_000
    assert result.loc[0, "ingested_at_utc"] == "20260713T145106Z"
    assert result.loc[0, "pipeline_run_id"] == "manual_20260713T145106Z"
    assert pd.api.types.is_numeric_dtype(result["total_volume"])


def test_normalize_protocols_coerces_ids_and_changes() -> None:
    payload = {
        "ingested_at_utc": "20260713T145110Z",
        "data": [
            {
                "id": "7",
                "name": "Example Protocol",
                "symbol": "EXP",
                "chain": "Ethereum",
                "category": "Lending",
                "tvl": "2500000.5",
                "change_1d": "-12.5",
                "change_7d": -20,
                "audits": "1",
            }
        ],
    }

    result = normalize_protocols(payload)

    assert result.loc[0, "id"] == 7
    assert result.loc[0, "tvl"] == 2_500_000.5
    assert result.loc[0, "change_1d"] == -12.5
    assert result.loc[0, "audits"] == 1


def test_normalize_stablecoins_extracts_usd_supply_and_chain_count() -> None:
    payload = {
        "ingested_at_utc": "20260713T145111Z",
        "data": {
            "peggedAssets": [
                {
                    "id": "8",
                    "name": "Example Dollar",
                    "symbol": "EXD",
                    "pegType": "peggedUSD",
                    "pegMechanism": "fiat-backed",
                    "price": 0.998,
                    "circulating": {"peggedUSD": 2_000_000},
                    "circulatingPrevDay": {"peggedUSD": 2_100_000},
                    "circulatingPrevWeek": {"peggedUSD": 2_200_000},
                    "chains": ["Ethereum", "Base"],
                }
            ]
        },
    }

    result = normalize_stablecoins(payload)

    assert result.loc[0, "id"] == 8
    assert result.loc[0, "circulating_usd"] == 2_000_000
    assert result.loc[0, "circulatingPrevDay_usd"] == 2_100_000
    assert result.loc[0, "chain_count"] == 2
    assert "chains" not in result.columns
