from pathlib import Path
import json

import pandas as pd


RAW_DIR = Path("data/raw/defillama/protocols")
OUTPUT_DIR = Path("data/processed/defillama")


def get_latest_file(raw_dir: Path) -> Path:
    files = sorted(raw_dir.glob("defillama_protocols_*.json"))
    if not files:
        raise FileNotFoundError(f"No raw files found in {raw_dir}")
    return files[-1]


def load_raw_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def normalize_protocols(payload: dict) -> pd.DataFrame:
    df = pd.DataFrame(payload["data"])

    columns = [
        "id",
        "name",
        "address",
        "symbol",
        "url",
        "description",
        "chain",
        "category",
        "tvl",
        "change_1h",
        "change_1d",
        "change_7d",
        "mcap",
        "listedAt",
        "audits",
        "audit_note",
        "gecko_id",
        "cmcId",
        "twitter",
        "forkedFrom",
        "module",
    ]

    available_columns = [col for col in columns if col in df.columns]
    df = df[available_columns].copy()

    df["ingested_at_utc"] = payload["ingested_at_utc"]

    numeric_columns = [
        "id",
        "tvl",
        "change_1h",
        "change_1d",
        "change_7d",
        "mcap",
        "listedAt",
        "audits",
        "cmcId",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    return df


def save_processed(df: pd.DataFrame, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    latest_path = output_dir / "protocols_latest.parquet"
    df.to_parquet(latest_path, index=False)

    ingested_at = pd.to_datetime(df["ingested_at_utc"].iloc[0])
    ingestion_date = ingested_at.strftime("%Y-%m-%d")
    timestamp = ingested_at.strftime("%Y%m%dT%H%M%SZ")

    snapshot_dir = Path("data/processed_snapshots/defillama/protocols") / (
        f"ingestion_date={ingestion_date}"
    )
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = snapshot_dir / f"protocols_{timestamp}.parquet"
    df.to_parquet(snapshot_path, index=False)

    return latest_path, snapshot_path


def main() -> None:
    raw_path = get_latest_file(RAW_DIR)
    payload = load_raw_payload(raw_path)
    df = normalize_protocols(payload)
    latest_path, snapshot_path = save_processed(df, OUTPUT_DIR)

    print(f"Loaded raw file: {raw_path}")
    print(f"Processed rows: {len(df)}")
    print(f"Saved latest to: {latest_path}")
    print(f"Saved snapshot to: {snapshot_path}")


if __name__ == "__main__":
    main()
