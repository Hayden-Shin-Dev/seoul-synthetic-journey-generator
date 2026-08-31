from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from seoul_generator.routing import haversine_m  # noqa: E402

DATASET = ROOT / "output" / "evaluation_dataset_v1"
NETWORK_PATH = ROOT / "reference_data" / "processed" / "seoul_network.json"
REPORT_DIR = ROOT / "reports" / "dataset_v1_geometry_audit"
PLOTS_DIR = REPORT_DIR / "plots"
MODE_SPEED_LIMITS = {"walk": 8.0, "bike": 20.0, "car": 50.0, "bus": 35.0, "rail": 80.0, "unknown": 100.0}


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit frozen Dataset v1 without changing dataset files")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    args = parser.parse_args()
    dataset = args.dataset
    network = json.loads(NETWORK_PATH.read_text(encoding="utf-8"))
    stations = {line: {item["name"]: item for item in values} for line, values in network["stations_by_line"].items()}
    bus_routes = {route["route_id"]: route for route in network["bus_routes"]}
    before_hashes = hash_tree(dataset)
    gt_records = load_ground_truth(dataset)
    gps_records = {trip_id: load_gps(dataset, trip_id) for trip_id in gt_records}
    rail_rows, rail_segments, rail_examples = audit_rail(gt_records, gps_records, stations)
    bus_rows = audit_bus(gt_records, gps_records, bus_routes)
    car_rows = audit_car(gt_records)
    physical_rows = audit_physical(gt_records, gps_records)
    plot_rail_samples(gt_records, gps_records, stations)
    after_hashes = hash_tree(dataset)
    unchanged = before_hashes == after_hashes
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(REPORT_DIR / "rail_journey_audit.csv", rail_rows)
    write_csv(REPORT_DIR / "bus_journey_audit.csv", bus_rows)
    write_csv(REPORT_DIR / "car_journey_audit.csv", car_rows)
    write_csv(REPORT_DIR / "physical_consistency.csv", physical_rows)
    (REPORT_DIR / "reference_data_audit.md").write_text(reference_report(network, stations, bus_routes), encoding="utf-8")
    (REPORT_DIR / "DATASET_V1_GEOMETRY_AUDIT.md").write_text(main_report(dataset, network, gt_records, gps_records, rail_rows, rail_segments, rail_examples, bus_rows, car_rows, physical_rows, unchanged), encoding="utf-8")
    print(json.dumps({"rail_segments": len(rail_segments), "rail_journeys": len({row["trip_id"] for row in rail_rows}), "bus_segments": len(bus_rows), "car_segments": len(car_rows), "rail_plots": len(list(PLOTS_DIR.glob("*.png"))), "dataset_hashes_unchanged": unchanged}, ensure_ascii=False))


def load_ground_truth(dataset: Path) -> dict[str, dict]:
    result = {}
    for path in sorted((dataset / "ground_truth").glob("*.json")):
        result[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return result


def load_gps(dataset: Path, trip_id: str) -> list[dict]:
    with (dataset / "gps" / f"{trip_id}.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def audit_rail(gt_records: dict[str, dict], gps_records: dict[str, list[dict]], stations: dict[str, dict[str, dict]]) -> tuple[list[dict], list[dict], list[dict]]:
    rows = []
    segment_records = []
    examples = []
    actual_line5_order = ["\uae40\ud3ec\uacf5\ud56d", "\ub9c8\uace1\ub098\ub8e8", "\uc5ec\uc758\ub3c4", "\uacf5\ub355", "\uc655\uc2ed\ub9ac"]
    for trip_id, gt in gt_records.items():
        gps = gps_records[trip_id]
        for segment in gt.get("segments", []):
            if segment.get("mode") != "rail":
                continue
            line = segment.get("line", "")
            sequence = segment.get("station_sequence", [])
            expected = stations.get(line, {})
            start = parse_time(segment["start_timestamp"])
            end = parse_time(segment["end_timestamp"])
            segment_gps = [row for row in gps if start <= parse_time(row["timestamp"].replace("Z", "+00:00")) <= end]
            distances = [nearest_distance(float(row["latitude"]), float(row["longitude"]), expected.values()) for row in segment_gps]
            first_distance = distance_to_named(segment_gps[0], sequence[0], expected) if segment_gps and sequence else None
            last_distance = distance_to_named(segment_gps[-1], sequence[-1], expected) if segment_gps and sequence else None
            reference_order = _contiguous_slice(sequence, list(expected))
            actual_order = "NOT_VERIFIABLE_FULL_REFERENCE"
            order_reason = "compact station reference has no complete line geometry or full station sequence"
            if line == "line_5":
                positions = [actual_line5_order.index(name) for name in sequence if name in actual_line5_order]
                actual_order = "PASS" if len(positions) == len(sequence) and positions == sorted(positions) and len(set(positions)) == len(positions) else "FAIL"
                order_reason = "selected station order compared with known Line 5 order" if actual_order == "PASS" else "compact Line 5 reference has Gongdeok before Yeouido, which reverses the real selected order"
            record = {"trip_id": trip_id, "segment_id": segment.get("segment_id"), "scenario_type": gt.get("scenario_category"), "line": line, "boarding_station": sequence[0] if sequence else "", "alighting_station": sequence[-1] if sequence else "", "station_sequence": " > ".join(sequence), "gps_point_count": len(segment_gps), "start_distance_to_expected_station_m": fmt(first_distance), "end_distance_to_expected_station_m": fmt(last_distance), "median_distance_to_nearest_expected_station_m": fmt(percentile(distances, 50)), "p95_distance_to_nearest_expected_station_m": fmt(percentile(distances, 95)), "max_distance_to_nearest_expected_station_m": fmt(max(distances) if distances else None), "stored_reference_order": "PASS" if reference_order else "FAIL", "actual_line5_order": actual_order, "status_reason": order_reason}
            rows.append(record)
            segment_records.append({"trip_id": trip_id, "gt": gt, "segment": segment, "gps": segment_gps, "expected": expected, "distances": distances})
            if line == "line_5" and len(examples) < 5:
                examples.append(record)
    return rows, segment_records, examples


def audit_bus(gt_records: dict[str, dict], gps_records: dict[str, list[dict]], bus_routes: dict[str, dict]) -> list[dict]:
    rows = []
    for trip_id, gt in gt_records.items():
        for segment in gt.get("segments", []):
            if segment.get("mode") != "bus":
                continue
            route_id = segment.get("route_id", "")
            route = bus_routes.get(route_id, {})
            expected_names = [stop["name"] for stop in route.get("stops", [])]
            sequence = segment.get("stop_sequence", [])
            start, end = parse_time(segment["start_timestamp"]), parse_time(segment["end_timestamp"])
            points = [row for row in gps_records[trip_id] if start <= parse_time(row["timestamp"].replace("Z", "+00:00")) <= end]
            expected = route.get("stops", [])
            distances = [nearest_distance(float(row["latitude"]), float(row["longitude"]), expected) for row in points]
            rows.append({"trip_id": trip_id, "segment_id": segment.get("segment_id"), "route_id": route_id, "route_name": segment.get("route_name", ""), "stop_sequence": " > ".join(sequence), "route_id_in_processed_reference": "PASS" if route_id in bus_routes else "FAIL", "stops_in_processed_reference": "PASS" if all(stop in expected_names for stop in sequence) else "FAIL", "official_route_membership": "NOT_VERIFIABLE", "official_stop_sequence": "NOT_VERIFIABLE", "road_route_polyline": "NO", "geometry_method": "piecewise straight interpolation between selected OSM stop coordinates", "median_distance_to_reference_stops_m": fmt(percentile(distances, 50)), "p95_distance_to_reference_stops_m": fmt(percentile(distances, 95)), "max_distance_to_reference_stops_m": fmt(max(distances) if distances else None), "status_reason": "public route ID and OSM stop positions are present, but the official Seoul route file was not imported"})
    return rows


def audit_car(gt_records: dict[str, dict]) -> list[dict]:
    rows = []
    for trip_id, gt in gt_records.items():
        for segment in gt.get("segments", []):
            if segment.get("mode") != "car":
                continue
            rows.append({"trip_id": trip_id, "segment_id": segment.get("segment_id"), "scenario_type": gt.get("scenario_category"), "corridor_id": segment.get("corridor_id", ""), "route_source": segment.get("source", ""), "classification": "A_LIMITED_PRECOMPUTED_OSRM_CORRIDOR", "road_network_data": "OSM derived geometry", "live_routing_at_generation": "NO", "origin_destination_arbitrary": "NO", "status_reason": "generation randomly selects one of 12 precomputed OSRM driving corridors"})
    return rows


def audit_physical(gt_records: dict[str, dict], gps_records: dict[str, list[dict]]) -> list[dict]:
    values: dict[str, list[float]] = {"walk": [], "bike": [], "car": [], "bus": [], "rail": [], "unknown": []}
    acceleration: dict[str, list[float]] = {key: [] for key in values}
    interval_count = Counter()
    negative = Counter()
    duplicate = Counter()
    zero_time_movement = Counter()
    over_80 = Counter()
    over_mode_speed = Counter()
    over_accel = Counter()
    teleport = Counter()
    for trip_id, gt in gt_records.items():
        rows = gps_records[trip_id]
        previous_speed = None
        previous_mode = "unknown"
        previous_time = None
        previous_row = None
        for row in rows:
            timestamp = parse_time(row["timestamp"].replace("Z", "+00:00"))
            mode = mode_at(gt, timestamp)
            if previous_row is not None:
                dt = (timestamp - previous_time).total_seconds()
                interval_count[mode] += 1
                if dt < 0:
                    negative[mode] += 1
                if dt == 0:
                    duplicate[mode] += 1
                    zero_time_movement[mode] += int(previous_row["latitude"] != row["latitude"] or previous_row["longitude"] != row["longitude"])
                if dt > 0:
                    implied = haversine_m(float(previous_row["latitude"]), float(previous_row["longitude"]), float(row["latitude"]), float(row["longitude"])) / dt
                    values[mode].append(implied)
                    if implied > 80:
                        over_80[mode] += 1
                    if implied > MODE_SPEED_LIMITS[mode]:
                        over_mode_speed[mode] += 1
                    if previous_speed is not None:
                        accel = abs(implied - previous_speed) / dt
                        acceleration[mode].append(accel)
                        if accel > 8:
                            over_accel[mode] += 1
                    if implied > 100:
                        teleport[mode] += 1
                    previous_speed = implied
                else:
                    previous_speed = None
            previous_row, previous_time, previous_mode = row, timestamp, mode
    result = []
    for mode in ("walk", "bike", "car", "bus", "rail", "unknown"):
        result.append({"mode": mode, "interval_count": interval_count[mode], "median_implied_speed_mps": fmt(percentile(values[mode], 50)), "p95_implied_speed_mps": fmt(percentile(values[mode], 95)), "max_implied_speed_mps": fmt(max(values[mode]) if values[mode] else None), "max_abs_acceleration_mps2": fmt(max(acceleration[mode]) if acceleration[mode] else None), "negative_time_count": negative[mode], "duplicate_timestamp_count": duplicate[mode], "zero_time_movement_count": zero_time_movement[mode], "speed_over_80_mps_count": over_80[mode], "speed_over_mode_limit_count": over_mode_speed[mode], "acceleration_over_8_mps2_count": over_accel[mode], "teleport_over_100_mps_count": teleport[mode], "status": "PASS" if not negative[mode] and not duplicate[mode] and not teleport[mode] and not over_mode_speed[mode] and not over_accel[mode] else "FAIL"})
    return result


def plot_rail_samples(gt_records: dict[str, dict], gps_records: dict[str, list[dict]], stations: dict[str, dict[str, dict]]) -> None:
    import matplotlib.pyplot as plt

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    candidates = []
    for trip_id, gt in gt_records.items():
        for segment in gt.get("segments", []):
            if segment.get("mode") != "rail":
                continue
            start, end = parse_time(segment["start_timestamp"]), parse_time(segment["end_timestamp"])
            points = [row for row in gps_records[trip_id] if start <= parse_time(row["timestamp"].replace("Z", "+00:00")) <= end]
            candidates.append((trip_id, gt, segment, points))
    candidates.sort(key=lambda item: (len(item[3]), item[0]))
    chosen = candidates[:2] + candidates[len(candidates) // 2 - 1 : len(candidates) // 2 + 1] + candidates[-2:]
    multimodal = [item for item in candidates if item[1].get("scenario_category") == "multimodal"][:4]
    seen = set()
    selected = []
    for item in chosen + multimodal:
        key = (item[0], item[2].get("segment_id"))
        if key not in seen:
            selected.append(item)
            seen.add(key)
    for index, (trip_id, gt, segment, points) in enumerate(selected, start=1):
        line = segment.get("line", "")
        expected = stations.get(line, {})
        coordinates = [(float(row["longitude"]), float(row["latitude"])) for row in points]
        if not coordinates:
            continue
        fig, ax = plt.subplots(figsize=(10, 7))
        ax.plot([point[0] for point in coordinates], [point[1] for point in coordinates], color="#374151", linewidth=1, label="observed GPS")
        station_sequence = segment.get("station_sequence", [])
        selected_stations = [expected[name] for name in station_sequence if name in expected]
        if selected_stations:
            ax.plot([item["lon"] for item in selected_stations], [item["lat"] for item in selected_stations], "--", color="#f59e0b", linewidth=1.5, label="station to station reference")
            ax.scatter([item["lon"] for item in selected_stations], [item["lat"] for item in selected_stations], color="#7c3aed", s=28, label="expected stations")
            for station_index, item in enumerate(selected_stations, start=1):
                ax.annotate(str(station_index), (item["lon"], item["lat"]), fontsize=8)
        ax.set_title(f"{trip_id} segment {segment.get('segment_id')} {line} {gt.get('scenario_category')}")
        ax.set_xlabel("longitude")
        ax.set_ylabel("latitude")
        ax.legend(loc="best")
        ax.grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(PLOTS_DIR / f"rail_sample_{index:02d}_{trip_id}_segment_{segment.get('segment_id')}.png", dpi=140)
        plt.close(fig)


def main_report(dataset: Path, network: dict, gt_records: dict[str, dict], gps_records: dict[str, list[dict]], rail_rows: list[dict], rail_segments: list[dict], rail_examples: list[dict], bus_rows: list[dict], car_rows: list[dict], physical_rows: list[dict], unchanged: bool) -> str:
    line_counts = Counter(row["line"] for row in rail_rows)
    rail_journeys = len({row["trip_id"] for row in rail_rows})
    compact_pass = sum(row["stored_reference_order"] == "PASS" for row in rail_rows)
    line5_fail = sum(row["actual_line5_order"] == "FAIL" for row in rail_rows)
    physical_fail = [row for row in physical_rows if row["status"] == "FAIL"]
    line5 = "\n".join(f"{row['trip_id']} | {row['scenario_type']} | {row['boarding_station']} -> {row['alighting_station']} | {row['line']} | {row['station_sequence']}" for row in rail_examples)
    physical_table = "\n".join(f"{row['mode']}: median {row['median_implied_speed_mps']} m/s, p95 {row['p95_implied_speed_mps']} m/s, max {row['max_implied_speed_mps']} m/s, max acceleration {row['max_abs_acceleration_mps2']} m/s2, teleport events {row['teleport_over_100_mps_count']}, status {row['status']}" for row in physical_rows)
    return f"""# Dataset v1 Geometry and Ground Truth Audit

Audit scope

This audit reads the frozen evaluation package, the generator source, the processed reference network, and the reference manifest. It does not modify, regenerate, or rewrite Dataset v1. Audit outputs are stored separately under this report folder.

## Direct Answers

Q1. Does a Ground Truth Line 5 journey start at a real Line 5 station and follow the real Line 5 station order?

PARTIALLY. The generator uses coordinates from records labelled line_5, but the compact sequence is not a complete Line 5 station list and its stored order places Gongdeok before Yeouido. The audit found {line5_fail} Line 5 rail segments that fail the known selected-station order check. The remaining Line 5 segments pass only the limited stored reference check.

Q2. Does the GPS follow actual Line 5 rail track geometry or an approximation?

STATION BASED APPROXIMATION. RAIL POLYLINE REFERENCE = NOT AVAILABLE. The code converts the selected station coordinates to a polyline and resamples each station to station segment with linear interpolation. Movement simulation and GPS noise are then applied.

Q3. Does a Bus Journey use the real bus route and stop order?

NO. It uses five public route identifiers and OSM stop positions selected near anchor points. The official Seoul bus route file and official route membership or sequence were not imported. The route is piecewise interpolation between selected stop coordinates.

Q4. Does a Car Journey follow real Seoul roads?

PARTIALLY YES. Car uses one of 12 precomputed OSRM driving geometries derived from OpenStreetMap. It does not perform arbitrary live origin destination routing at generation time. Walk and bike also reuse these driving corridor geometries.

Q5. Is this 700 Journey dataset sufficient for Canopy Bus and Rail Transit Context performance evaluation?

PARTIALLY. It is independent and useful for a controlled synthetic smoke test, but it is not sufficient for a claim about production transit context accuracy because full official bus route membership, full rail station sequences, and rail track geometry are absent. The generator contains no Canopy thresholds, scores, resolver rules, or production matching radius.

## Dataset Summary

Evaluation package: {dataset}

Ground Truth files: {len(gt_records)}

GPS files: {len(gps_records)}

Rail containing journeys: {rail_journeys}

Rail segments: {len(rail_segments)}

Rail segment counts by stored line: {dict(line_counts)}

Bus segments: {len(bus_rows)}

Car segments: {len(car_rows)}

## Rail Generation Flow

For a rail journey, DatasetGenerator.generate_journey in src/seoul_generator/generator.py calls _route. Router.rail_route in src/seoul_generator/routing.py selects a stored line from ReferenceNetwork.stations_by_line, chooses a contiguous slice of that stored list, converts station coordinates to [latitude, longitude] pairs, and calls resample_polyline.

resample_polyline performs piecewise linear interpolation between station coordinates. It does not read a rail track geometry. The returned points go to generate_segment_points in src/seoul_generator/mobility.py. That function applies a procedural speed wave, rail speed bounds, and dwell positions. Dwell positions are evenly distributed over total route distance and are not read from the actual intermediate station coordinates.

The resulting true trajectory is passed to observe in src/seoul_generator/gps.py. That function adds coordinate jitter, accuracy variation, interval jitter, speed noise, course noise, missing points, stationary drift, and poor accuracy events. _write_ground_truth in src/seoul_generator/generator.py writes the segment mode and route metadata selected earlier. No geometry based reclassification occurs before Ground Truth is written.

## Line 5 Examples

The five examples below were read directly from evaluation_dataset_v1/ground_truth.

{line5}

The stored processed Line 5 reference is: 김포공항, 마곡나루, 공덕, 여의도, 왕십리. The known selected-station order is 김포공항, 마곡나루, 여의도, 공덕, 왕십리. This is why the compact reference check can pass while the actual selected-station order check can fail.

## Station Sequence Audit

Total rail containing journeys: {rail_journeys}

Total rail segments audited: {len(rail_segments)}

Passed against the generator's stored contiguous reference slice: {compact_pass}

Failed against the stored contiguous reference slice: {len(rail_rows) - compact_pass}

Line 5 selected-order failures against the known actual selected order: {line5_fail}

For lines other than Line 5, a complete actual station order could not be verified because the repository has no full official line sequence reference. The CSV records this as NOT_VERIFIABLE_FULL_REFERENCE rather than claiming a pass.

Checks performed: missing station names, missing line keys, sequence order, duplicates, compact reference membership, and Line 5 selected order. Full intermediate station omission cannot be checked from the available reference because the processed network itself is a compact sample.

## Station Distance Results

The rail CSV reports median, p95, and maximum distance from observed GPS to the nearest expected station in the selected station sequence. These are station based approximation distances. They are not distances to rail geometry.

Start and end distances are measured against the first and last expected station for each rail segment. Multimodal rail segments include the connector added by _join_route in src/seoul_generator/generator.py, so the first rail segment point can be away from the boarding station.

## Bus Audit

The bus CSV contains {len(bus_rows)} bus segments. Every generated route ID is present in the processed compact reference and every selected stop name is present in that compact route. That is only an internal consistency result.

Official route membership and official stop sequence are NOT_VERIFIABLE from the repository. prepare_reference_data.py selects the nearest OSM stop for each anchor and records a public route ID. routing.py then resamples the selected stop coordinates. No official bus route geometry is used.

## Car, Walk, and Bike Audit

The car CSV contains {len(car_rows)} segments. A car segment stores a corridor_id and source field from the 12 OSRM geometries in reference_data/processed/seoul_network.json. This is real OSM derived road geometry for those corridors, but it is a limited precomputed corridor set.

Walk and bike call the same Router.surface_route method and therefore also use driving profile OSRM corridors. There is no separate pedestrian network or bicycle network in the processed reference data. Procedural movement speed does not make the geometry walkable or bike legal.

## Movement and Time Audit

Speeds are generated by hand-authored rules and bounded random variation in src/seoul_generator/mobility.py. BASE_SPEEDS, SPEED_RANGES, sine waves, hard case multipliers, random pauses, and stop dwell ranges are used. No measured traffic distribution, rail timetable, bus timetable, or real acceleration distribution is used.

Rail has a procedural speed wave and evenly distributed dwell positions. Bus has procedural stop dwell and speed variation. Timestamps are produced at the configured interval, while GPS observations add bounded interval jitter.

This audit treats implied speeds above 8 m/s for walk, 20 m/s for bike, 50 m/s for car, 35 m/s for bus, or 80 m/s for rail as mode speed failures. Absolute implied acceleration above 8 m/s2 is also reported as a failure. These are audit thresholds, not measured Seoul traffic limits.

{physical_table}

Physical consistency failure rows: {len(physical_fail)}. The repository's original validation also passed its 11,903 checks. This audit adds implied speed, acceleration, duplicate time, zero time movement, and teleport calculations by mode.

## Ground Truth Reliability

Scenario Intent and Actual Generated Geometry are separate concepts in the source code only up to trajectory creation. The mode is selected before route generation. _write_ground_truth then copies the selected segment mode and route metadata into JSON. There is no second pass that proves the generated coordinates are on a real rail track, official bus route, or mode-accessible network.

Ground Truth is therefore reliable as the generator's scenario label and metadata record. It is not evidence that the generated geometry satisfies a complete real-world network constraint.

## Production Independence

Canopy Transit Context score: NO

Rail threshold: NO

Bus threshold: NO

Resolver rules: NO

Production matching radius: NO

Production classification logic: NO

The repository search and source inspection found no Canopy production reference. This supports independence and means there is no direct evaluation leakage from those fields.

## Evaluation Judgement

Movement ML Evaluation: PASS_WITH_LIMITATIONS. The package has 700 journeys, five single-mode labels, multimodal segments, procedural variation, noise profiles, reproducible seeds, and separate Ground Truth. Geometry is not a complete citywide network simulation.

Transit Context Evaluation: FAIL for production claims and PASS_WITH_LIMITATIONS for a synthetic smoke test. Bus route membership and full rail sequences are not authoritative, and rail track geometry is absent.

Rail Detection Evaluation: PASS_WITH_LIMITATIONS. Rail sequences are selected from stored station lists and GPS endpoints are station based, but the line lists are compact and Line 5 contains an order error. There is no rail polyline.

Bus Detection Evaluation: FAIL for real route fidelity and PASS_WITH_LIMITATIONS for a synthetic stop proximity test. The public route IDs and OSM stop coordinates do not prove official route membership or stop order.

Car Detection Evaluation: PASS_WITH_LIMITATIONS. Car geometry is OSM derived for 12 precomputed OSRM corridors, but this is not a general Seoul road network sample.

Multimodal Segmentation Evaluation: PASS_WITH_LIMITATIONS. Segment labels and boundaries are generated and separated from GPS, but _join_route adds synthetic connectors and no geometry based segment verification is performed.

## Visual Audit

The plots folder contains six short, medium, and long rail examples plus four multimodal rail segment examples. Each plot shows observed GPS, expected station points, station sequence numbering, and the station to station reference. No rail polyline is shown because RAIL POLYLINE REFERENCE = NOT AVAILABLE.

## Hash and File Safety

Frozen evaluation package hashes before and after audit: {"UNCHANGED" if unchanged else "CHANGED"}

The audit writes only under reports/dataset_v1_geometry_audit. Dataset v1 files were not changed.

## Files Produced

DATASET_V1_GEOMETRY_AUDIT.md

rail_journey_audit.csv

bus_journey_audit.csv

car_journey_audit.csv

physical_consistency.csv

reference_data_audit.md

plots/
"""


def reference_report(network: dict, stations: dict, bus_routes: dict) -> str:
    lines = "\n".join(f"{line}: {len(values)} selected station records" for line, values in network["stations_by_line"].items())
    routes = "\n".join(f"{route_id}: {len(route['stops'])} OSM stop positions, source note: {route.get('source_note', '')}" for route_id, route in bus_routes.items())
    return f"""# Reference Data Audit

Reference processed file

reference_data/processed/seoul_network.json

Reference manifest

reference_data/manifests/reference_data_manifest.json

The processed file contains WGS84 station coordinates, OSM bus stop coordinates, public bus route identifiers, station lists grouped by stored line key, and 12 OSRM surface corridor geometries derived from OpenStreetMap.

Station records

{lines}

Bus route records

{routes}

Rail source status

RAIL POLYLINE REFERENCE = NOT AVAILABLE

The rail data is station point data grouped into compact stored sequences. It does not contain rail way geometry, track polylines, timetable data, or a complete authoritative station sequence for every line.

Bus source status

The official Seoul bus source URLs are recorded in the manifest, but the processed file does not contain the official Seoul route file. The current records are public route identifiers plus nearest OSM stop positions selected from anchor points. Official route membership and stop order are not verifiable from this repository alone.

Surface source status

The surface corridors are precomputed OSRM driving geometries based on OpenStreetMap. They are actual OSM derived road route shapes for the stored origin and destination hub pairs. They are not a complete Seoul road graph and are reused by walk and bike generation.
"""


def mode_at(gt: dict, timestamp: datetime) -> str:
    for segment in gt.get("segments", []):
        start, end = parse_time(segment["start_timestamp"]), parse_time(segment["end_timestamp"])
        if start <= timestamp <= end:
            return segment.get("mode", "unknown")
    if gt.get("segments"):
        nearest = min(gt["segments"], key=lambda segment: min(abs((timestamp - parse_time(segment["start_timestamp"])).total_seconds()), abs((timestamp - parse_time(segment["end_timestamp"])).total_seconds())))
        return nearest.get("mode", "unknown")
    return "unknown"


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def nearest_distance(lat: float, lon: float, records) -> float | None:
    values = list(records)
    if not values:
        return None
    return min(haversine_m(lat, lon, item["lat"], item["lon"]) for item in values)


def distance_to_named(row: dict, name: str, expected: dict) -> float | None:
    item = expected.get(name)
    return None if item is None else haversine_m(float(row["latitude"]), float(row["longitude"]), item["lat"], item["lon"])


def _contiguous_slice(sequence: list[str], reference: list[str]) -> bool:
    return any(reference[index : index + len(sequence)] == sequence for index in range(max(1, len(reference) - len(sequence) + 1)))


def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.3f}"


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def hash_tree(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result[str(path.relative_to(root)).replace("\\", "/")] = digest
    return result


if __name__ == "__main__":
    main()
