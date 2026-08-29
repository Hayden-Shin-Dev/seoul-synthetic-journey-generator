from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Locate generated representative trajectory views")
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    visual_dir = args.dataset / "visualizations"
    index = visual_dir / "index.html"
    if not index.exists():
        raise SystemExit("no visual samples found; generate the dataset first")
    samples = sorted(path.name for path in visual_dir.glob("*.html") if path.name != "index.html")
    print(f"visual sample index: {index}")
    print(f"sample count: {len(samples)}")
    for sample in samples:
        print(sample)


if __name__ == "__main__":
    main()

