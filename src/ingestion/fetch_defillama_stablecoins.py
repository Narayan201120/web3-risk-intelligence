from datetime import datetime, timezone
from pathlib import Path
import json
import requests


BASE_URL = "https://stablecoins.llama.fi/stablecoins"


def fetch_stablecoins() -> dict:
    params = {"includePrices": "true"}

    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def save_raw_json(data: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"defillama_stablecoins_{run_timestamp}.json"

    payload = {
        "source": "defillama",
        "endpoint": BASE_URL,
        "ingested_at_utc": run_timestamp,
        "record_count": len(data.get("peggedAssets", [])),
        "data": data,
    }

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)

    return output_path


def main() -> None:
    data = fetch_stablecoins()
    output_path = save_raw_json(data, Path("data/raw/defillama/stablecoins"))
    print(f"Saved {len(data.get('peggedAssets', []))} records to {output_path}")


if __name__ == "__main__":
    main()
