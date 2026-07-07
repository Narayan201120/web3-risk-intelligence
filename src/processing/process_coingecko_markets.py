from pathlib import Path
import json

import pandas as pd

RAW_DIR = Path("data/raw/coingecko/markets")
OUTPUT_DIR = Path("data/processed/coingecko")

def get_latest_file(raw_dir: Path) -> Path:
    files = sorted(raw_dir.glob("coingecko_markets_*.json"))
    if not files:
        raise FileNotFoundError(f"No raw files found in {raw_dir}")
    return files[-1]

def load_raw_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)
    
def normalize_markets(payload: dict) -> pd.DataFrame:
    df = pd.DataFrame(payload["data"])
    
    columns = [
        "id",
        "symbol",
        "name",
        "current_price",
        "market_cap",
        "market_cap_rank",
        "total_volume",
        "high_24h",
        "low_24h",
        "price_change_percentage_24h",
        "price_change_percentage_1h_in_currency",
        "price_change_percentage_24h_in_currency",
        "price_change_percentage_7d_in_currency",
        "circulating_supply",
        "total_supply",
        "max_supply",
        "ath",
        "ath_change_percentage",
        "atl",
        "atl_change_percentage",
        "last_updated",
    ]
    
    available_columns = [col for col in columns if col in df.columns]
    df = df[available_columns].copy()
    
    df["ingested_at_utc"] = payload["ingested_at_utc"]
    df["source_file"] = str(payload.get("source", "coingecko"))

    numeric_columns = [
        "current_price",
        "market_cap",
        "market_cap_rank",
        "total_volume",
        "high_24h",
        "low_24h",
        "price_change_percentage_24h",
        "price_change_percentage_1h_in_currency",
        "price_change_percentage_24h_in_currency",
        "price_change_percentage_7d_in_currency",
        "circulating_supply",
        "total_supply",
        "max_supply",
        "ath",
        "ath_change_percentage",
        "atl",
        "atl_change_percentage",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if "last_updated" in df.columns:
        df["last_updated"] = pd.to_datetime(df["last_updated"], errors="coerce")

    return df


def save_processed(df: pd.DataFrame, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "markets_latest.parquet"
    df.to_parquet(output_path, index=False)
    return output_path


def main() -> None:
    raw_path = get_latest_file(RAW_DIR)
    payload = load_raw_payload(raw_path)
    df = normalize_markets(payload)
    output_path = save_processed(df, OUTPUT_DIR)

    print(f"Loaded raw file: {raw_path}")
    print(f"Processed rows: {len(df)}")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()