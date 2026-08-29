from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the evaluation-only dataset package")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    for name in ("gps", "ground_truth"):
        shutil.copytree(args.dataset / name, args.destination / name, dirs_exist_ok=True)
    for name in ("dataset_manifest.json", "journey_manifest.csv", "reference_data_manifest.json", "freeze_manifest.json"):
        source = args.dataset / "manifests" / name
        if name == "reference_data_manifest.json":
            source = Path(__file__).resolve().parents[1] / "reference_data" / "manifests" / name
        if source.exists():
            shutil.copy2(source, args.destination / name)
    validation = args.dataset / "validation" / "validation_report.json"
    if validation.exists():
        shutil.copy2(validation, args.destination / "validation_report.json")
    print(f"exported evaluation package to {args.destination}")


if __name__ == "__main__":
    main()
