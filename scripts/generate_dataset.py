from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from seoul_generator.config import load_config  # noqa: E402
from seoul_generator.generator import DatasetGenerator  # noqa: E402
from seoul_generator.reference import ReferenceNetwork  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate GPS and Ground Truth files")
    parser.add_argument("--poc", action="store_true", help="generate the small validation dataset")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    config = load_config(ROOT / "config")
    configured = config["generator"]["journey_counts"]
    counts = {mode: configured[f"poc_{mode}"] if args.poc else configured[mode] for mode in ("walk", "bike", "car", "bus", "rail", "multimodal")}
    version = "poc" if args.poc else config["generator"]["dataset_version"]
    output_dir = args.output or ROOT / "output" / version
    generator = DatasetGenerator(config, ReferenceNetwork(ROOT / "reference_data" / "processed" / "seoul_network.json"))
    manifest = generator.generate_dataset(output_dir, counts, configured["poc_hard_case"] if args.poc else 20)
    print(f"generated {manifest['journey_count']} journeys and {manifest['gps_event_count']} GPS events at {output_dir}")


if __name__ == "__main__":
    main()

