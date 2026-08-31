from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from seoul_generator.v3_generator import DatasetGeneratorV3  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a real-reference Dataset v3 candidate")
    parser.add_argument("--full", action="store_true", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "evaluation_dataset_v3_candidate")
    parser.add_argument("--seed", type=int, default=52026)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        if not args.force:
            raise SystemExit(f"output is not empty, use --force for a generated v3 directory: {output}")
        shutil.rmtree(output)
    counts = {"walk": 120, "bike": 110, "car": 110, "bus": 100, "rail": 120, "multimodal": 140}
    manifest = DatasetGeneratorV3(ROOT, args.seed).generate(output, counts)
    manifest["candidate_stage"] = "full"
    (output / "manifests" / "dataset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "dataset_version": manifest["dataset_version"], "journey_count": manifest["journey_count"], "counts": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
