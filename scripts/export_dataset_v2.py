from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the frozen Dataset v2 evaluation package")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    destination = args.destination.resolve()
    freeze = dataset / "manifests" / "freeze_manifest.json"
    if not freeze.exists():
        raise SystemExit("Dataset v2 must be frozen before export")
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("gps", "ground_truth"):
        shutil.copytree(dataset / name, destination / name, dirs_exist_ok=True)
    for name in ("dataset_manifest.json", "journey_manifest.csv", "freeze_manifest.json"):
        shutil.copy2(dataset / "manifests" / name, destination / name)
    shutil.copy2(ROOT / "reference_data" / "v2" / "reference_data_manifest.json", destination / "reference_data_manifest.json")
    shutil.copy2(dataset / "validation" / "validation_report.json", destination / "validation_report.json")
    print(f"exported frozen Dataset v2 evaluation package to {destination}")


if __name__ == "__main__":
    main()
