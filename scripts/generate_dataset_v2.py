from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from seoul_generator.v2_generator import DatasetGeneratorV2  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a real-reference Dataset v2 candidate")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prototype", action="store_true")
    group.add_argument("--pilot", action="store_true")
    group.add_argument("--full", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.prototype:
        counts, default_seed, default_output, line5 = {"walk": 10, "bike": 10, "car": 10, "bus": 10, "rail": 10, "multimodal": 10}, 22026, ROOT / "output" / "dataset_v2_prototype", 5
    elif args.pilot:
        counts, default_seed, default_output, line5 = {"walk": 9, "bike": 8, "car": 8, "bus": 8, "rail": 9, "multimodal": 8}, 32026, ROOT / "output" / "dataset_v2_pilot", 0
    else:
        counts, default_seed, default_output, line5 = {"walk": 120, "bike": 110, "car": 110, "bus": 100, "rail": 120, "multimodal": 140}, 42026, ROOT / "output" / "evaluation_dataset_v2_candidate", 0

    output = (args.output or default_output).resolve()
    if output.exists() and any(output.iterdir()):
        if not args.force:
            raise SystemExit(f"output is not empty, use --force only for a generated v2 directory: {output}")
        shutil.rmtree(output)
    seed = args.seed if args.seed is not None else default_seed
    manifest = DatasetGeneratorV2(ROOT, seed).generate(output, counts, line5)
    manifest["candidate_stage"] = "prototype" if args.prototype else "pilot" if args.pilot else "full"
    (output / "manifests" / "dataset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "seed": seed, "journey_count": manifest["journey_count"], "counts": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
