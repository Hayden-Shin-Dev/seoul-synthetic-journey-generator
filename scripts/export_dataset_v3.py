from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the frozen Dataset v3 evaluation package")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    destination = args.destination.resolve()
    if json.loads((dataset / "manifests" / "freeze_manifest.json").read_text(encoding="utf-8")).get("status") != "FROZEN":
        raise SystemExit("Dataset v3 must be frozen before export")
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("gps", "ground_truth"):
        shutil.copytree(dataset / name, destination / name, dirs_exist_ok=True)
    for name in ("dataset_manifest.json", "journey_manifest.csv", "freeze_manifest.json"):
        shutil.copy2(dataset / "manifests" / name, destination / name)
    shutil.copy2(ROOT / "reference_data" / "v3" / "reference_data_manifest.json", destination / "reference_data_manifest.json")
    for name in ("validation_report.json", "point_validation.csv", "journey_reality_validation.csv", "mode_reality_validation.csv", "multimodal_reality_validation.csv", "release_gate.json", "JOURNEY_REALITY_VALIDATION.md"):
        shutil.copy2(dataset / "validation" / name, destination / name)
    freeze_path = destination / "freeze_manifest.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    freeze["package_file_hashes"] = {str(path.relative_to(destination)).replace("\\", "/"): sha256(path) for path in sorted(destination.rglob("*")) if path.is_file() and path.name != "freeze_manifest.json"}
    freeze["package_file_count"] = len(freeze["package_file_hashes"])
    freeze["package_status"] = "FROZEN"
    freeze_path.write_text(json.dumps(freeze, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"exported frozen Dataset v3 evaluation package to {destination}")


if __name__ == "__main__":
    main()
