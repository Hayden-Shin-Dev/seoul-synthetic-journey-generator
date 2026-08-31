from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_network_v2 as base  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Dataset v3 regional rail and mode-specific networks")
    parser.add_argument("--pbf", type=Path, default=ROOT / "reference_data" / "v3" / "raw" / "south-korea-latest.osm.pbf")
    args = parser.parse_args()
    base.OUT = ROOT / "reference_data" / "v3"
    base.GRAPH_DIR = base.OUT / "graphs"
    base.RAIL_PATH = base.OUT / "rail_network.json"
    base.RAIL_VALIDATION_PATH = base.OUT / "rail_reference_validation.csv"
    sys.argv = [sys.argv[0], "--pbf", str(args.pbf)]
    base.main()


if __name__ == "__main__":
    main()
