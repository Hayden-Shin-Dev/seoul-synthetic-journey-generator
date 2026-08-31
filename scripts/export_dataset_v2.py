from __future__ import annotations

import argparse
import hashlib
import json
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
    freeze_path = destination / "freeze_manifest.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    package_hashes = {}
    for path in sorted(destination.rglob("*")):
        if path.is_file() and path.name != "freeze_manifest.json":
            package_hashes[str(path.relative_to(destination)).replace("\\", "/")] = sha256(path)
    freeze["package_file_count"] = len(package_hashes)
    freeze["package_file_hashes"] = package_hashes
    freeze["package_status"] = "FROZEN"
    freeze_path.write_text(json.dumps(freeze, ensure_ascii=False, indent=2), encoding="utf-8")
    package_manifest_path = destination / "dataset_manifest.json"
    package_manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
    package_manifest["freeze"]["package_status"] = "FROZEN"
    package_manifest["freeze"]["package_file_count"] = len(package_hashes)
    package_manifest_path.write_text(json.dumps(package_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"exported frozen Dataset v2 evaluation package to {destination}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
