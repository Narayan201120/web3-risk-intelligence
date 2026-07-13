import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

STEPS = [
    "src/ingestion/fetch_coingecko_markets.py",
    "src/ingestion/fetch_defillama_protocols.py",
    "src/ingestion/fetch_defillama_stablecoins.py",
    "src/processing/process_coingecko_markets.py",
    "src/processing/process_defillama_protocols.py",
    "src/processing/process_defillama_stablecoins.py",
    "src/analytics/token_liquidity_risk.py",
    "src/analytics/token_liquidity_risk_trends.py",
    "src/analytics/defi_protocol_risk.py",
    "src/analytics/defi_protocol_risk_trends.py",
    "src/analytics/stablecoin_depeg_risk.py",
    "src/quality/check_outputs.py",
]


def run_step(script_path: str) -> None:
    print(f"\nRunning {script_path}")

    result = subprocess.run(
        [sys.executable, script_path],
        cwd=PROJECT_ROOT,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Pipeline failed at step: {script_path}")


def main() -> None:
    for step in STEPS:
        run_step(step)

    print("\nPipeline completed successfully.")


if __name__ == "__main__":
    main()