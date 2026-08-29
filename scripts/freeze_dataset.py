from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from seoul_generator.validation import validate_dataset  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze a validated dataset")
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    report = validate_dataset(args.dataset)
    if report["failed"]:
        raise SystemExit(f"refusing to freeze invalid dataset: {report['failed']} failed checks")
    manifest_path = args.dataset / "manifests" / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reference_manifest = ROOT / "reference_data" / "manifests" / "reference_data_manifest.json"
    config_hash = manifest["config_hash"]
    file_hashes = {}
    for path in sorted(args.dataset.rglob("*")):
        if path.is_file() and path.name != "freeze_manifest.json":
            file_hashes[str(path.relative_to(args.dataset)).replace("\\", "/")] = _sha256(path)
    git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    freeze = {
        "dataset_version": manifest["dataset_version"],
        "generator_version": manifest["generator_version"],
        "git_commit": git_commit,
        "seed": manifest["seed"],
        "reference_data_hash": _sha256(reference_manifest),
        "config_hash": config_hash,
        "file_hashes": file_hashes,
        "frozen_at": datetime.now(UTC).isoformat(),
        "validation": {"status": report["status"], "passed": report["passed"], "failed": report["failed"]},
    }
    manifest["freeze"] = {"status": "frozen", "git_commit": git_commit, "frozen_at": freeze["frozen_at"]}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.dataset / "manifests" / "freeze_manifest.json").write_text(json.dumps(freeze, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"frozen {manifest['dataset_version']} at {git_commit}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()

