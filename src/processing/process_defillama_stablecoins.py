from pathlib import Path
import json

import pandas as pd


RAW_DIR = Path("data/raw/defillama/stablecoins")
OUTPUT_DIR = Path("data/processed/defillama")


def get_latest_file(raw_dir: Path) -> Path:
    files = sorted(raw_dir.glob("defillama_stablecoins_*.json"))
    if not files:
        raise FileNotFoundError(f"No raw files found in {raw_dir}")
    return files[-1]


def load_raw_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_pegged_usd(value: object) -> float | None:
    if isinstance(value, dict):
        return value.get("peggedUSD")
    return None


def normalize_stablecoins(payload: dict) -> pd.DataFrame:
    assets = payload["data"].get("peggedAssets", [])
    df = pd.DataFrame(assets)

    columns = [
        "id",
        "name",
        "symbol",
        "gecko_id",
        "pegType",
        "pegMechanism",
        "price",
        "circulating",
        "circulatingPrevDay",
        "circulatingPrevWeek",
        "circulatingPrevMonth",
        "chains",
    ]

    available_columns = [col for col in columns if col in df.columns]
    df = df[available_columns].copy()

    df["ingested_at_utc"] = payload["ingested_at_utc"]

    for column in [
        "circulating",
        "circulatingPrevDay",
        "circulatingPrevWeek",
        "circulatingPrevMonth",
    ]:
        if column in df.columns:
            df[f"{column}_usd"] = df[column].apply(get_pegged_usd)

    if "chains" in df.columns:
        df["chain_count"] = df["chains"].apply(
            lambda value: len(value) if isinstance(value, list) else None
        )

    numeric_columns = [
        "id",
        "price",
        "circulating_usd",
        "circulatingPrevDay_usd",
        "circulatingPrevWeek_usd",
        "circulatingPrevMonth_usd",
        "chain_count",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    drop_columns = [
        "circulating",
        "circulatingPrevDay",
        "circulatingPrevWeek",
        "circulatingPrevMonth",
        "chains",
    ]

    df = df.drop(columns=[col for col in drop_columns if col in df.columns])

    return df


def save_processed(df: pd.DataFrame, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "stablecoins_latest.parquet"
    df.to_parquet(output_path, index=False)
    return output_path


def main() -> None:
    raw_path = get_latest_file(RAW_DIR)
    payload = load_raw_payload(raw_path)
    df = normalize_stablecoins(payload)
    output_path = save_processed(df, OUTPUT_DIR)

    print(f"Loaded raw file: {raw_path}")
    print(f"Processed rows: {len(df)}")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()