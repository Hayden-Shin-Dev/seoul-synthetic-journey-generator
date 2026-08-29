from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .gps import GPS_COLUMNS
from .models import MODES
from .routing import haversine_m

LEAKAGE_TERMS = {"mode", "label", "route", "line", "station", "stop", "ground_truth", "scenario", "synthetic"}


def validate_dataset(dataset_dir: Path) -> dict:
    checks: list[dict] = []
    gps_dir = dataset_dir / "gps"
    gt_dir = dataset_dir / "ground_truth"
    gps_files = sorted(gps_dir.glob("*.csv"))
    gt_files = sorted(gt_dir.glob("*.json"))
    _check(checks, "gps files present", bool(gps_files), f"found {len(gps_files)} GPS files")
    _check(checks, "ground truth files present", bool(gt_files), f"found {len(gt_files)} Ground Truth files")
    _check(checks, "GPS and Ground Truth file counts match", len(gps_files) == len(gt_files), f"GPS={len(gps_files)} GroundTruth={len(gt_files)}")
    for gps_path in gps_files:
        trip_id = gps_path.stem
        gt_path = gt_dir / f"{trip_id}.json"
        rows, fieldnames = _read_csv(gps_path)
        _check(checks, f"{trip_id}: GPS schema", fieldnames == GPS_COLUMNS, "schema mismatch")
        _check(checks, f"{trip_id}: no Ground Truth leakage", not (set(fieldnames) & LEAKAGE_TERMS), "forbidden field present")
        _check(checks, f"{trip_id}: nonempty journey", bool(rows), "no GPS rows")
        if rows:
            _validate_gps_rows(checks, trip_id, rows)
        _check(checks, f"{trip_id}: Ground Truth exists", gt_path.exists(), "missing Ground Truth")
        if gt_path.exists():
            ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))
            _validate_ground_truth(checks, trip_id, rows, ground_truth)
    passed = sum(item["passed"] for item in checks)
    failed = len(checks) - passed
    return {"dataset_dir": str(dataset_dir), "gps_file_count": len(gps_files), "ground_truth_file_count": len(gt_files), "check_count": len(checks), "passed": passed, "failed": failed, "status": "passed" if failed == 0 else "failed", "checks": checks}


def _validate_gps_rows(checks: list[dict], trip_id: str, rows: list[dict]) -> None:
    timestamps = [datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")) for row in rows]
    sequences = [int(row["sequence"]) for row in rows]
    _check(checks, f"{trip_id}: timestamp monotonicity", timestamps == sorted(timestamps) and len(set(timestamps)) == len(timestamps), "timestamps are not strictly increasing")
    _check(checks, f"{trip_id}: sequence monotonicity", sequences == list(range(len(rows))), "sequence is not contiguous")
    _check(checks, f"{trip_id}: valid coordinates", all(-90 <= float(row["latitude"]) <= 90 and -180 <= float(row["longitude"]) <= 180 for row in rows), "invalid coordinate")
    _check(checks, f"{trip_id}: no missing coordinates", all(row["latitude"] and row["longitude"] for row in rows), "missing coordinate")
    _check(checks, f"{trip_id}: valid accuracy", all(float(row["horizontal_accuracy_m"]) > 0 and float(row["vertical_accuracy_m"]) > 0 for row in rows), "invalid accuracy")
    _check(checks, f"{trip_id}: realistic speed field", all(0 <= float(row["speed_mps"]) <= 80 for row in rows), "unrealistic speed field")
    duplicate_events = any(a["timestamp"] == b["timestamp"] and a["latitude"] == b["latitude"] and a["longitude"] == b["longitude"] for a, b in zip(rows, rows[1:]))
    _check(checks, f"{trip_id}: duplicate events", not duplicate_events, "duplicate adjacent event")
    teleport = False
    for first, second, first_time, second_time in zip(rows, rows[1:], timestamps, timestamps[1:]):
        seconds = max(0.1, (second_time - first_time).total_seconds())
        speed = haversine_m(float(first["latitude"]), float(first["longitude"]), float(second["latitude"]), float(second["longitude"])) / seconds
        teleport = teleport or speed > 100
    _check(checks, f"{trip_id}: impossible teleportation", not teleport, "consecutive points exceed 100 m/s")


def _validate_ground_truth(checks: list[dict], trip_id: str, rows: list[dict], ground_truth: dict) -> None:
    _check(checks, f"{trip_id}: GPS and Ground Truth trip_id consistency", ground_truth.get("trip_id") == trip_id, "trip_id mismatch")
    segments = ground_truth.get("segments", [])
    _check(checks, f"{trip_id}: segments present", bool(segments), "missing segments")
    parsed = []
    valid_modes = True
    for segment in segments:
        try:
            start = datetime.fromisoformat(segment["start_timestamp"])
            end = datetime.fromisoformat(segment["end_timestamp"])
            parsed.append((start, end))
        except (KeyError, ValueError):
            continue
        valid_modes = valid_modes and segment.get("mode") in MODES
        if segment.get("mode") == "rail":
            valid_modes = valid_modes and bool(segment.get("line")) and len(segment.get("station_sequence", [])) >= 2
        if segment.get("mode") == "bus":
            valid_modes = valid_modes and bool(segment.get("route_id")) and len(segment.get("stop_sequence", [])) >= 2
    _check(checks, f"{trip_id}: valid modes and transit metadata", valid_modes, "invalid mode or transit metadata")
    _check(checks, f"{trip_id}: segment order", all(start <= end for start, end in parsed) and all(parsed[index][1] <= parsed[index + 1][0] for index in range(len(parsed) - 1)), "segment overlap or inversion")
    if rows and parsed:
        gps_times = [datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")) for row in rows]
        _check(checks, f"{trip_id}: GPS timestamps map to Ground Truth", min(gps_times) >= parsed[0][0] and max(gps_times) <= parsed[-1][1] + (parsed[-1][1] - parsed[-1][0]), "GPS timestamp outside segment bounds")


def _read_csv(path: Path) -> tuple[list[dict], list[str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), reader.fieldnames or []


def _check(checks: list[dict], name: str, passed: bool, detail: str) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})

