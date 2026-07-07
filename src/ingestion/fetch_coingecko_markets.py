from datetime import datetime, timezone
from pathlib import Path
import json
import requests

BASE_URL = "https://api.coingecko.com/api/v3/coins/markets"

def fetch_markets(page: int = 1, per_page: int = 250) -> list[dict]:
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": per_page,
        "page": page,
        "sparkline": "false",
        "price_change_percentage": "1h,24h,7d",
    }
    
    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()

def save_raw_json(data: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    
    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"coingecko_markets_{run_timestamp}.json"
    payload = {
        "source": "coingecko",
        "endpoint": BASE_URL,
        "ingested_at_utc": run_timestamp,
        "record_count": len(data),
        "data": data,
    }
    
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
    
    return output_path


def main() -> None:
    data = fetch_markets(page=1, per_page=250)
    output_path = save_raw_json(data, Path("data/raw/coingecko/markets"))
    print(f"Saved {len(data)} records to {output_path}")
    
if __name__ == "__main__":
    main()