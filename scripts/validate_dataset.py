from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from seoul_generator.validation import validate_dataset  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a generated dataset")
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    report = validate_dataset(args.dataset)
    validation_dir = args.dataset / "validation"
    validation_dir.mkdir(exist_ok=True)
    (validation_dir / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "check_count", "passed", "failed")}, ensure_ascii=False))
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

