from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "data/runs"

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
    "src/analytics/stablecoin_depeg_risk_trends.py",
    "src/analytics/build_risk_observations.py",
    "src/alerts/emit_risk_alerts.py",
    "src/quality/check_outputs.py",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_manifest(manifest: dict[str, object], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = manifest_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(manifest_path)


def run_step(
    script_path: str,
    environment: dict[str, str],
    manifest: dict[str, object],
    manifest_path: Path,
) -> None:
    print(f"\nRunning {script_path}")
    step = {
        "script": script_path,
        "status": "running",
        "started_at_utc": utc_now(),
    }
    steps = manifest["steps"]
    if not isinstance(steps, list):
        raise TypeError("Pipeline manifest steps must be a list")
    steps.append(step)
    write_manifest(manifest, manifest_path)

    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
    )
    step["finished_at_utc"] = utc_now()
    step["duration_seconds"] = round(time.perf_counter() - started, 3)

    if result.returncode != 0:
        step["status"] = "failed"
        write_manifest(manifest, manifest_path)
        raise RuntimeError(f"Pipeline failed at step: {script_path}")

    step["status"] = "succeeded"
    write_manifest(manifest, manifest_path)


def main() -> None:
    started_at_utc = utc_now()
    run_id = f"run_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    manifest_path = RUNS_ROOT / run_id / "manifest.json"
    manifest: dict[str, object] = {
        "pipeline_run_id": run_id,
        "started_at_utc": started_at_utc,
        "finished_at_utc": None,
        "status": "running",
        "steps": [],
    }

    environment = os.environ.copy()
    environment["PIPELINE_RUN_ID"] = run_id
    environment["PIPELINE_STARTED_AT_UTC"] = started_at_utc
    environment["PIPELINE_MANIFEST_PATH"] = str(manifest_path)
    project_path = str(PROJECT_ROOT)
    existing_python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        project_path
        if not existing_python_path
        else project_path + os.pathsep + existing_python_path
    )

    write_manifest(manifest, manifest_path)
    print(f"Pipeline run: {run_id}")

    try:
        for step in STEPS:
            run_step(step, environment, manifest, manifest_path)
    except Exception as error:
        manifest["status"] = "failed"
        manifest["finished_at_utc"] = utc_now()
        manifest["error"] = str(error)
        write_manifest(manifest, manifest_path)
        raise

    manifest["status"] = "succeeded"
    manifest["finished_at_utc"] = utc_now()
    write_manifest(manifest, manifest_path)
    print(f"Manifest: {manifest_path}")
    print("\nPipeline completed successfully.")


if __name__ == "__main__":
    main()
