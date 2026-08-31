from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from seoul_generator.v2_routing import haversine_m  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Independently validate Dataset v2")
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    report = validate(args.dataset.resolve())
    validation = args.dataset / "validation"
    validation.mkdir(parents=True, exist_ok=True)
    (validation / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "journey_count", "check_count", "passed", "failed")}, ensure_ascii=False))
    if report["failed"]:
        raise SystemExit(1)


def validate(dataset: Path) -> dict:
    checks: list[dict] = []
    geometry_rows: list[dict] = []
    physical_rows: list[dict] = []
    multimodal_rows: list[dict] = []
    point_rows: list[dict] = []
    mode_rows: dict[str, list[dict]] = {mode: [] for mode in ("rail", "bus", "car", "walk", "bike")}
    gps_files = sorted((dataset / "gps").glob("*.csv"))
    gt_files = sorted((dataset / "ground_truth").glob("*.json"))
    add(checks, "gps_ground_truth_file_count", len(gps_files) == len(gt_files), f"gps={len(gps_files)} ground_truth={len(gt_files)}")
    ids = {path.stem for path in gps_files}
    add(checks, "matching_trip_files", ids == {path.stem for path in gt_files}, "GPS and Ground Truth stems match")
    counts = Counter()
    max_speed = 0.0
    min_interval = float("inf")
    max_interval = 0.0
    for gt_path in gt_files:
        trip_id = gt_path.stem
        payload = json.loads(gt_path.read_text(encoding="utf-8"))
        segments = payload.get("segments", [])
        category = payload.get("scenario_category")
        counts[category] += 1
        add(checks, f"{trip_id}_segments_present", bool(segments), "segment list is nonempty")
        add(checks, f"{trip_id}_segment_times_ordered", _segment_times_ordered(segments), "segment times are ordered")
        all_geo_ok = True
        for segment in segments:
            mode = segment.get("mode")
            geo = segment.get("geometry_validation", {})
            geo_ok = geo.get("status") == "PASS" and geo.get("method") == "resampled_along_actual_reference_polyline"
            all_geo_ok = all_geo_ok and geo_ok
            geometry_rows.append({"trip_id": trip_id, "segment_id": segment.get("segment_id"), "mode": mode, "status": geo.get("status", "FAIL"), "method": geo.get("method", ""), "reference_distance_m": geo.get("reference_distance_m", ""), "max_error_m": geo.get("trajectory_point_to_reference_max_m", ""), "p95_error_m": geo.get("trajectory_point_to_reference_p95_m", "")})
            mode_rows.get(mode, []).append({"trip_id": trip_id, "segment_id": segment.get("segment_id"), "status": "PASS" if _mode_metadata_ok(mode, segment) and geo_ok else "FAIL", "reference": segment.get("route_reference") or segment.get("rail_geometry_reference") or segment.get("route_geometry_reference", "")})
            if mode in {"rail", "bus"}:
                add(checks, f"{trip_id}_segment_{segment.get('segment_id')}_{mode}_metadata", _mode_metadata_ok(mode, segment), "mode-specific reference metadata present")
        add(checks, f"{trip_id}_reference_geometry", all_geo_ok, "every segment follows actual reference geometry")
        gps_path = dataset / "gps" / f"{trip_id}.csv"
        rows = list(csv.DictReader(gps_path.open(encoding="utf-8", newline=""))) if gps_path.exists() else []
        gps_ok, gps_stats = _gps_checks(rows, trip_id)
        add(checks, f"{trip_id}_gps_contract", gps_ok, "GPS schema, coordinates, sequence, and timestamps")
        max_speed = max(max_speed, gps_stats["max_speed"])
        min_interval = min(min_interval, gps_stats["min_interval"])
        max_interval = max(max_interval, gps_stats["max_interval"])
        true_path = dataset / "true_trajectories" / f"{trip_id}.json"
        true_data = json.loads(true_path.read_text(encoding="utf-8")) if true_path.exists() else {}
        physical_ok, physical = _physical_checks(true_path)
        add(checks, f"{trip_id}_physical_constraints", physical_ok, "true trajectory has no teleport and remains under speed cap")
        physical_rows.append({"trip_id": trip_id, **physical})
        point_ok, trip_points, _point_stats = _point_checks(rows, true_data)
        point_rows.extend({"trip_id": trip_id, **item} for item in trip_points)
        add(checks, f"{trip_id}_point_level_network_fidelity", point_ok, f"{len(trip_points)} GPS points have separate true and observed network distances")
        add(checks, f"{trip_id}_origin_validity", _endpoint_validity(rows, true_data, first=True), "first observed fix is near the generated origin")
        add(checks, f"{trip_id}_destination_validity", _endpoint_validity(rows, true_data, first=False), "last observed fix is near the generated destination")
        add(checks, f"{trip_id}_gt_consistency", _gt_consistency(segments, true_data), "Ground Truth segment modes and IDs match true trajectory")
        transfers = payload.get("post_generation_validation", {}).get("transfers", [])
        transfer_ok = all(item.get("validity") == "PASS" for item in transfers)
        add(checks, f"{trip_id}_transfer_distance", transfer_ok, "all segment transfers are within 450m")
        if category == "multimodal":
            multimodal_rows.append({"trip_id": trip_id, "segment_count": len(segments), "modes": ">".join(segment.get("mode", "") for segment in segments), "status": "PASS" if transfer_ok and all_geo_ok else "FAIL"})
    add(checks, "journey_manifest_count", _manifest_count(dataset) == len(gps_files), "manifest count equals files")
    add(checks, "gps_speed_cap", max_speed <= 35.0, f"max reported speed {max_speed:.3f}m/s")
    add(checks, "gps_interval_range", min_interval >= 3.5 and max_interval <= 35.0, f"observed interval range {min_interval:.3f}-{max_interval:.3f}s including explicitly modelled missing fixes")
    add(checks, "category_counts", sum(counts.values()) == len(gps_files) and all(counts[category] > 0 for category in ("walk", "bike", "car", "bus", "rail", "multimodal")), str(dict(counts)))
    _write_rows(dataset / "validation" / "geometry_validation.csv", geometry_rows)
    _write_rows(dataset / "validation" / "physical_validation.csv", physical_rows)
    _write_rows(dataset / "validation" / "point_validation.csv", point_rows)
    _write_rows(dataset / "validation" / "multimodal_validation.csv", multimodal_rows)
    for mode, rows in mode_rows.items():
        _write_rows(dataset / "validation" / f"{mode}_validation.csv", rows)
    passed = sum(item["status"] == "PASS" for item in checks)
    failed = len(checks) - passed
    return {"dataset_version": "evaluation_dataset_v2", "status": "PASS" if failed == 0 else "FAIL", "journey_count": len(gps_files), "category_counts": dict(counts), "gps_point_count": len(point_rows), "point_validation_pass": sum(item.get("physical_status") == "PASS" for item in point_rows), "point_validation_fail": sum(item.get("physical_status") != "PASS" for item in point_rows), "check_count": len(checks), "passed": passed, "failed": failed, "max_reported_speed_mps": round(max_speed, 3), "observed_interval_seconds": [round(min_interval, 3) if min_interval != float("inf") else None, round(max_interval, 3)], "checks": checks}


def add(checks: list[dict], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})


def _segment_times_ordered(segments: list[dict]) -> bool:
    try:
        times = [(datetime.fromisoformat(item["start_time"]), datetime.fromisoformat(item["end_time"])) for item in segments]
        return all(start <= end for start, end in times) and all(times[i][1] <= times[i + 1][0] for i in range(len(times) - 1))
    except (KeyError, ValueError):
        return False


def _point_to_geometry_m(point: tuple[float, float], geometry: list[list[float]]) -> float:
    if len(geometry) < 2:
        return float("inf")
    scale_x = 111_320.0 * max(0.2, math.cos(math.radians(point[0])))
    scale_y = 111_320.0
    px, py = point[1] * scale_x, point[0] * scale_y
    best = float("inf")
    for first, second in zip(geometry, geometry[1:]):
        ax, ay = first[1] * scale_x, first[0] * scale_y
        bx, by = second[1] * scale_x, second[0] * scale_y
        dx, dy = bx - ax, by - ay
        denominator = dx * dx + dy * dy
        fraction = 0.0 if denominator == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denominator))
        best = min(best, math.hypot(px - (ax + fraction * dx), py - (ay + fraction * dy)))
    return best


def _point_checks(rows: list[dict], true_data: dict) -> tuple[bool, list[dict], dict]:
    true_points = true_data.get("points", [])
    true_segments = {int(item["segment_id"]): item.get("reference_geometry", []) for item in true_data.get("segments", [])}
    if not rows or not true_points or not true_segments:
        return False, [], {"count": 0}
    true_times = [datetime.fromisoformat(item["timestamp"]).timestamp() for item in true_points]
    output = []
    previous_observed = None
    for sequence, row in enumerate(rows):
        observed_time = datetime.fromisoformat(row["timestamp"]).timestamp()
        index = bisect.bisect_left(true_times, observed_time)
        index = min(max(index, 0), len(true_points) - 1)
        if index and abs(true_times[index - 1] - observed_time) <= abs(true_times[index] - observed_time):
            index -= 1
        truth = true_points[index]
        mode = truth.get("mode", "")
        expected = {"walk": "pedestrian_osm_network", "bike": "bicycle_osm_network", "car": "drivable_osm_road_network", "bus": "official_bus_route_plus_osm_road_network", "rail": "osm_railway_relation_geometry"}.get(mode, "unknown")
        geometry = true_segments.get(int(truth.get("segment_id", 0)), [])
        true_coord = (float(truth["lat"]), float(truth["lon"]))
        observed_coord = (float(row["latitude"]), float(row["longitude"]))
        implied = 0.0
        if previous_observed is not None:
            seconds = observed_time - previous_observed[0]
            implied = haversine_m(previous_observed[1], observed_coord) / seconds if seconds > 0 else float("inf")
        previous_observed = (observed_time, observed_coord)
        true_distance = _point_to_geometry_m(true_coord, geometry)
        observed_distance = _point_to_geometry_m(observed_coord, geometry)
        physical_status = "PASS" if true_distance <= 35.0 and implied <= 80.0 else "FAIL"
        output.append({"sequence": sequence, "timestamp": row["timestamp"], "mode_gt_from_separate_gt": mode, "true_lat": truth["lat"], "true_lon": truth["lon"], "observed_lat": row["latitude"], "observed_lon": row["longitude"], "expected_network_type": expected, "true_distance_to_network_m": round(true_distance, 3), "observed_distance_to_network_m": round(observed_distance, 3), "distance_to_expected_network": round(observed_distance, 3), "implied_speed": round(implied, 3) if math.isfinite(implied) else "inf", "physical_status": physical_status})
    return all(item["physical_status"] == "PASS" for item in output), output, {"count": len(output)}


def _endpoint_validity(rows: list[dict], true_data: dict, first: bool) -> bool:
    if not rows or not true_data.get("origin") or not true_data.get("destination"):
        return False
    row = rows[0] if first else rows[-1]
    target = true_data["origin"] if first else true_data["destination"]
    return haversine_m((float(row["latitude"]), float(row["longitude"])), (float(target[0]), float(target[1]))) <= 200.0


def _gt_consistency(segments: list[dict], true_data: dict) -> bool:
    expected = [(int(item["segment_id"]), item.get("mode")) for item in segments]
    actual = []
    seen = set()
    for item in true_data.get("points", []):
        value = (int(item["segment_id"]), item.get("mode"))
        if value not in seen:
            seen.add(value)
            actual.append(value)
    return bool(expected) and expected == actual


def _mode_metadata_ok(mode: str, segment: dict) -> bool:
    if mode in {"walk", "bike", "car"}:
        return segment.get("routing_profile") == mode and str(segment.get("route_reference", "")).startswith(f"local_osm_{mode}_graph")
    if mode == "bus":
        reference = str(segment.get("route_geometry_reference", ""))
        profile = segment.get("routing_profile")
        return bool(segment.get("route_id")) and len(segment.get("stop_sequence", [])) >= 3 and ((reference.startswith("local_osm_car_graph_route_") and profile == "car_graph_for_bus_road_geometry") or (reference.startswith("osm_bus_relation_") and profile == "bus_on_osm_road_graph"))
    if mode == "rail":
        return bool(segment.get("line")) and bool(segment.get("relation_id")) and len(segment.get("station_sequence", [])) >= 3 and str(segment.get("rail_geometry_reference", "")).startswith("osm_rail_relation_")
    return False


def _gps_checks(rows: list[dict], trip_id: str) -> tuple[bool, dict]:
    required = {"schema_version", "trip_id", "device_id", "sequence", "timestamp", "latitude", "longitude", "horizontal_accuracy_m", "speed_mps", "course_deg"}
    allowed = required | {"altitude_m", "vertical_accuracy_m"}
    try:
        times = [datetime.fromisoformat(row["timestamp"]) for row in rows]
        sequences = [int(row["sequence"]) for row in rows]
        intervals = [(second - first).total_seconds() for first, second in zip(times, times[1:])]
        ok = bool(rows) and required.issubset(rows[0]) and set(rows[0]).issubset(allowed) and all(row["trip_id"] == trip_id for row in rows) and sequences == list(range(len(rows))) and times == sorted(times) and len(times) == len(set(times)) and all(-90 <= float(row["latitude"]) <= 90 and -180 <= float(row["longitude"]) <= 180 and float(row["horizontal_accuracy_m"]) > 0 and 0 <= float(row["speed_mps"]) <= 35 for row in rows)
        return ok, {"max_speed": max(float(row["speed_mps"]) for row in rows), "min_interval": min(intervals, default=0), "max_interval": max(intervals, default=0)}
    except (KeyError, ValueError, TypeError):
        return False, {"max_speed": 999.0, "min_interval": 0, "max_interval": 999.0}


def _physical_checks(path: Path) -> tuple[bool, dict]:
    if not path.exists():
        return False, {"status": "FAIL", "point_count": 0, "max_derived_speed_mps": 999.0, "max_step_m": 999.0, "max_acceleration_mps2": 999.0}
    data = json.loads(path.read_text(encoding="utf-8"))
    points = data.get("points", [])
    speeds = []
    steps = []
    accelerations = []
    for first, second in zip(points, points[1:]):
        seconds = (datetime.fromisoformat(second["timestamp"]) - datetime.fromisoformat(first["timestamp"])).total_seconds()
        distance = haversine_m((float(first["lat"]), float(first["lon"])), (float(second["lat"]), float(second["lon"])))
        steps.append(distance)
        if seconds > 0:
            speeds.append(distance / seconds)
            if first.get("speed_mps") is not None and second.get("speed_mps") is not None:
                accelerations.append(abs(float(second["speed_mps"]) - float(first["speed_mps"])) / seconds)
    maximum = max(speeds, default=0.0)
    max_acceleration = max(accelerations, default=0.0)
    ok = bool(points) and all((datetime.fromisoformat(second["timestamp"]) - datetime.fromisoformat(first["timestamp"])).total_seconds() > 0 for first, second in zip(points, points[1:])) and maximum <= 35.0 and max(steps, default=0.0) <= 250.0 and max_acceleration <= 8.0
    return ok, {"status": "PASS" if ok else "FAIL", "point_count": len(points), "max_derived_speed_mps": round(maximum, 3), "max_step_m": round(max(steps, default=0.0), 3), "max_acceleration_mps2": round(max_acceleration, 3)}


def _manifest_count(dataset: Path) -> int:
    path = dataset / "manifests" / "dataset_manifest.json"
    return int(json.loads(path.read_text(encoding="utf-8")).get("journey_count", -1)) if path.exists() else -1


def _write_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("status\nPASS\n", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
