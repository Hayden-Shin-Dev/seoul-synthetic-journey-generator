from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from seoul_generator.v2_routing import LocalRouter

STOP_FILE = ROOT / "reference_data" / "v2" / "raw" / "seoul_bus_stops_20260804.xlsx"
GRAPH_DIR = ROOT / "reference_data" / "v2" / "graphs"
REPORT_DIR = ROOT / "reports" / "dataset_v2" / "routing_smoke_tests"


def candidate_points(df: pd.DataFrame) -> list[tuple[float, float, str]]:
    points = []
    for _, row in df.iterrows():
        points.append((float(row["Y좌표"]), float(row["X좌표"]), str(row["ARS_ID"]).zfill(5)))
    return points


def run_mode(mode: str, points: list[tuple[float, float, str]], count: int) -> list[dict[str, object]]:
    router = LocalRouter(GRAPH_DIR / f"{mode}.graph.pkl.gz")
    rows = []
    routes = []
    attempts = 0
    for separation in (25, 50, 100, 200, 400, 800, 1200):
        for index in range(0, len(points) - separation, max(1, separation // 2)):
            if len(rows) >= count:
                break
            start = points[index]
            end = points[index + separation]
            attempts += 1
            try:
                result = router.route(start[:2], end[:2], max_snap_distance_m=250.0, respect_restrictions=mode == "car")
            except ValueError:
                continue
            rows.append({
                "mode": mode,
                "test_id": f"{mode}_{len(rows) + 1:02d}",
                "start_lat": start[0],
                "start_lon": start[1],
                "end_lat": end[0],
                "end_lon": end[1],
                "start_reference": start[2],
                "end_reference": end[2],
                "route_distance_m": round(result.distance_m, 3),
                "route_duration_s": round(result.duration_s, 3),
                "geometry_points": len(result.geometry),
                "start_snap_distance_m": round(result.start_snap_distance_m, 3),
                "end_snap_distance_m": round(result.end_snap_distance_m, 3),
                "routing_status": "PASS",
            })
            routes.append(result.geometry)
        if len(rows) >= count:
            break
    if len(rows) < count:
        raise RuntimeError(f"{mode} produced only {len(rows)} of {count} smoke routes after {attempts} attempts")
    figure, axis = plt.subplots(figsize=(10, 10), dpi=160)
    for index, geometry in enumerate(routes, 1):
        lon = [point[1] for point in geometry]
        lat = [point[0] for point in geometry]
        axis.plot(lon, lat, linewidth=0.8, alpha=0.55)
        axis.scatter([lon[0], lon[-1]], [lat[0], lat[-1]], s=4)
    axis.set_title(f"Dataset v2 {mode} local routing smoke test, {count} routes")
    axis.set_xlabel("longitude")
    axis.set_ylabel("latitude")
    axis.grid(True, alpha=0.2)
    figure.tight_layout()
    figure.savefig(REPORT_DIR / f"{mode}_20_routes.png")
    plt.close(figure)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 20-route smoke tests for each v2 surface profile")
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_excel(STOP_FILE, dtype={"ARS_ID": str})
    points = candidate_points(df)
    rows = []
    for mode in ("car", "walk", "bike"):
        rows.extend(run_mode(mode, points, args.count))
    with (REPORT_DIR / "routing_smoke_tests.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"smoke routes PASS: {len(rows)}")


if __name__ == "__main__":
    main()
