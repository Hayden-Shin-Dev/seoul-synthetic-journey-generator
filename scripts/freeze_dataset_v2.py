from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from validate_dataset_v2 import validate  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze a validated Dataset v2")
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    report = validate(dataset)
    if report["failed"]:
        raise SystemExit(f"refusing to freeze invalid Dataset v2: {report['failed']} failed checks")
    manifest_path = dataset / "manifests" / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reference_manifest = ROOT / "reference_data" / "v2" / "reference_data_manifest.json"
    config = ROOT / "config" / "generator_v2.yaml"
    files = {str(path.relative_to(dataset)).replace("\\", "/"): sha256(path) for path in sorted(dataset.rglob("*")) if path.is_file() and path.name != "freeze_manifest.json"}
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    frozen_at = datetime.now(UTC).isoformat()
    freeze = {"dataset_version": "evaluation_dataset_v2", "generator_version": manifest.get("generator_version", "2.0.0"), "git_commit": commit, "seed": manifest["seed"], "reference_manifest_sha256": sha256(reference_manifest), "generator_config_sha256": sha256(config), "file_count": len(files), "file_hashes": files, "validation": {"status": report["status"], "passed": report["passed"], "failed": report["failed"]}, "frozen_at": frozen_at, "status": "FROZEN"}
    manifest["freeze"] = {"status": "FROZEN", "git_commit": commit, "frozen_at": frozen_at}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (dataset / "manifests" / "freeze_manifest.json").write_text(json.dumps(freeze, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "FROZEN", "dataset": str(dataset), "git_commit": commit, "file_count": len(files)}))


if __name__ == "__main__":
    main()
