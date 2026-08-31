from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from seoul_generator.v2_routing import haversine_m  # noqa: E402


COLORS = {"walk": "#2f6f8f", "bike": "#3d8b5f", "car": "#b55239", "bus": "#8a5a9a", "rail": "#d18b24"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot Dataset v2 true route and GPS observations")
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    output = dataset / "visualizations"
    output.mkdir(parents=True, exist_ok=True)
    rail = json.loads((ROOT / "reference_data" / "v2" / "rail_network.json").read_text(encoding="utf-8"))
    bus = json.loads((ROOT / "reference_data" / "v2" / "bus_network.json").read_text(encoding="utf-8"))
    station_by_name = {station["name"]: (station["lat"], station["lon"]) for line in rail["lines"] for station in line["station_sequence"]}
    stop_by_ars = {stop["ars_id"]: (stop["lat"], stop["lon"]) for route in bus["routes"] for stop in route.get("stops", [])}
    count = 0
    for gt_path in sorted((dataset / "ground_truth").glob("*.json")):
        trip_id = gt_path.stem
        truth = json.loads((dataset / "true_trajectories" / f"{trip_id}.json").read_text(encoding="utf-8"))["points"]
        with (dataset / "gps" / f"{trip_id}.csv").open(encoding="utf-8", newline="") as handle:
            observed = list(csv.DictReader(handle))
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        figure, axis = plt.subplots(figsize=(8, 8), dpi=130)
        for mode in sorted({point["mode"] for point in truth}, key=lambda item: list(COLORS).index(item)):
            points = [point for point in truth if point["mode"] == mode]
            axis.plot([point["lon"] for point in points], [point["lat"] for point in points], color=COLORS[mode], linewidth=1.7, label=f"true {mode}")
        axis.scatter([float(point["longitude"]) for point in observed], [float(point["latitude"]) for point in observed], s=3, color="#555555", alpha=0.45, label="observed GPS")
        axis.scatter([truth[0]["lon"], truth[-1]["lon"]], [truth[0]["lat"], truth[-1]["lat"]], s=35, color=("#111111", "#ffffff"), edgecolors="#111111", zorder=4, label="start/end")
        for segment in gt.get("segments", []):
            coords = []
            if segment.get("mode") == "rail":
                coords = [station_by_name[name] for name in segment.get("station_sequence", []) if name in station_by_name]
            elif segment.get("mode") == "bus":
                coords = [stop_by_ars[ars] for ars in segment.get("stop_sequence", []) if ars in stop_by_ars]
            if coords:
                axis.scatter([lon for lat, lon in coords], [lat for lat, lon in coords], s=12, facecolors="none", edgecolors=COLORS[segment["mode"]], linewidths=0.8)
        axis.set_title(f"{trip_id} {gt.get('scenario_category', '')}")
        axis.set_xlabel("longitude")
        axis.set_ylabel("latitude")
        axis.grid(alpha=0.2)
        axis.legend(loc="best", fontsize=7)
        figure.tight_layout()
        figure.savefig(output / f"{trip_id}.png")
        plt.close(figure)
        count += 1
    print(f"wrote {count} Dataset v2 journey plots to {output}")


if __name__ == "__main__":
    main()
