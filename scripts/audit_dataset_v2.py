from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit an existing Dataset v2 candidate without generating data")
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    report = json.loads((dataset / "validation" / "validation_report.json").read_text(encoding="utf-8"))
    manifest = json.loads((dataset / "manifests" / "dataset_manifest.json").read_text(encoding="utf-8"))
    checks = {
        "validation_report_pass": report.get("status") == "PASS" and report.get("failed") == 0,
        "manifest_count_matches_gps": manifest.get("journey_count") == len(list((dataset / "gps").glob("*.csv"))),
        "ground_truth_count_matches_gps": len(list((dataset / "ground_truth").glob("*.json"))) == len(list((dataset / "gps").glob("*.csv"))),
        "reference_manifest_present": (Path(__file__).resolve().parents[1] / "reference_data" / "v2" / "reference_data_manifest.json").exists(),
    }
    output = {"dataset": str(dataset), "dataset_version": manifest.get("dataset_version"), "journey_count": manifest.get("journey_count"), "checks": {name: "PASS" if value else "FAIL" for name, value in checks.items()}, "status": "PASS" if all(checks.values()) else "FAIL", "manifest_sha256": sha256(dataset / "manifests" / "dataset_manifest.json")}
    path = dataset / "validation" / "independent_audit_report.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))
    if output["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
