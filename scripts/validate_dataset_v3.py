from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_dataset_v2 import validate  # noqa: E402


def main() -> None:
    dataset = Path(sys.argv[1]).resolve()
    report = validate(dataset)
    report["dataset_version"] = "evaluation_dataset_v3"
    (dataset / "validation" / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "journey_count", "check_count", "passed", "failed")}, ensure_ascii=False))
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
