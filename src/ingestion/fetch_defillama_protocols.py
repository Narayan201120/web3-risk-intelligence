from datetime import datetime, timezone
from pathlib import Path
import json
import requests


BASE_URL = "https://api.llama.fi/protocols"


def fetch_protocols() -> list[dict]:
    response = requests.get(BASE_URL, timeout=30)
    response.raise_for_status()
    return response.json()


def save_raw_json(data: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"defillama_protocols_{run_timestamp}.json"

    payload = {
        "source": "defillama",
        "endpoint": BASE_URL,
        "ingested_at_utc": run_timestamp,
        "record_count": len(data),
        "data": data,
    }

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)

    return output_path


def main() -> None:
    data = fetch_protocols()
    output_path = save_raw_json(data, Path("data/raw/defillama/protocols"))
    print(f"Saved {len(data)} records to {output_path}")


if __name__ == "__main__":
    main()