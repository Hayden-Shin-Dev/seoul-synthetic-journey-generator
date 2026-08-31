from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import Journey, Point, Segment
from .v2_routing import LocalRouter, RouteResult, haversine_m


UTC9 = timezone(timedelta(hours=9))
GPS_COLUMNS = ["schema_version", "trip_id", "device_id", "sequence", "timestamp", "latitude", "longitude", "horizontal_accuracy_m", "altitude_m", "vertical_accuracy_m", "speed_mps", "course_deg"]
MODES = ("walk", "bike", "car", "bus", "rail")
NOISE = {
    "clean": {"sigma": 2.0, "accuracy": (4.0, 10.0), "missing": 0.002, "speed_sigma": 0.12, "course_sigma": 3.0},
    "normal": {"sigma": 5.0, "accuracy": (5.0, 25.0), "missing": 0.015, "speed_sigma": 0.3, "course_sigma": 7.0},
    "noisy": {"sigma": 9.0, "accuracy": (8.0, 55.0), "missing": 0.04, "speed_sigma": 0.55, "course_sigma": 14.0},
}
BASE_SPEED = {"walk": 1.35, "bike": 4.8, "car": 10.0, "bus": 7.5, "rail": 13.5}
MAX_SPEED = {"walk": 2.6, "bike": 11.0, "car": 30.0, "bus": 22.0, "rail": 30.0}


@dataclass
class RouteSpec:
    mode: str
    geometry: list[tuple[float, float]]
    metadata: dict[str, Any]
    stop_offsets_m: list[float]
    route_distance_m: float


def bearing(first: tuple[float, float], second: tuple[float, float]) -> float:
    y = math.sin(math.radians(second[1] - first[1])) * math.cos(math.radians(second[0]))
    x = math.cos(math.radians(first[0])) * math.sin(math.radians(second[0])) - math.sin(math.radians(first[0])) * math.cos(math.radians(second[0])) * math.cos(math.radians(second[1] - first[1]))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def point_at_distance(geometry: list[tuple[float, float]], cumulative: list[float], distance: float) -> tuple[float, float]:
    distance = max(0.0, min(cumulative[-1], distance))
    for index in range(len(cumulative) - 1):
        if cumulative[index + 1] >= distance:
            span = cumulative[index + 1] - cumulative[index]
            fraction = 0.0 if span == 0 else (distance - cumulative[index]) / span
            return (geometry[index][0] + (geometry[index + 1][0] - geometry[index][0]) * fraction, geometry[index][1] + (geometry[index + 1][1] - geometry[index][1]) * fraction)
    return geometry[-1]


def geometry_distance(geometry: list[tuple[float, float]]) -> float:
    return sum(haversine_m(first, second) for first, second in zip(geometry, geometry[1:]))


def point_to_segment_m(point: tuple[float, float], first: tuple[float, float], second: tuple[float, float]) -> float:
    scale_x = 111_320.0 * max(0.2, math.cos(math.radians(point[0])))
    scale_y = 111_320.0
    px, py = point[1] * scale_x, point[0] * scale_y
    ax, ay = first[1] * scale_x, first[0] * scale_y
    bx, by = second[1] * scale_x, second[0] * scale_y
    dx, dy = bx - ax, by - ay
    denominator = dx * dx + dy * dy
    fraction = 0.0 if denominator == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denominator))
    return math.hypot(px - (ax + fraction * dx), py - (ay + fraction * dy))


def geometry_metrics(points: list[Point], reference_geometry: list[tuple[float, float]]) -> dict[str, Any]:
    if len(reference_geometry) < 2:
        return {"status": "FAIL", "reason": "reference geometry has fewer than two points"}
    errors = []
    for point in points:
        errors.append(min(point_to_segment_m((point.lat, point.lon), first, second) for first, second in zip(reference_geometry, reference_geometry[1:])))
    geometry_hash = hashlib.sha256(json.dumps(reference_geometry, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"status": "PASS" if max(errors, default=float("inf")) <= 35.0 else "FAIL", "method": "resampled_along_actual_reference_polyline", "reference_geometry_hash": geometry_hash, "reference_point_count": len(reference_geometry), "reference_distance_m": round(geometry_distance(reference_geometry), 3), "trajectory_point_to_reference_max_m": round(max(errors, default=0.0), 3), "trajectory_point_to_reference_p95_m": round(sorted(errors)[max(0, math.ceil(len(errors) * 0.95) - 1)], 3)}


class ReferenceV2:
    def __init__(self, root: Path) -> None:
        reference = root / "reference_data" / "v2"
        self.root = root
        self.rail = [item for item in json.loads((reference / "rail_network.json").read_text(encoding="utf-8"))["lines"] if item["validation"]["status"] == "PASS" and len(item["station_sequence"]) >= 3]
        self.bus = [item for item in json.loads((reference / "bus_network.json").read_text(encoding="utf-8"))["routes"] if item["validation"]["status"] == "PASS" and len(item.get("pair_geometry", [])) == len(item.get("stops", [])) - 1 and all(pair.get("geometry") for pair in item.get("pair_geometry", []))]
        self.bus_stops = [stop for route in self.bus for stop in route["stops"]]
        self._routers: dict[str, LocalRouter] = {}
        self._rail_indices: dict[int, list[int]] = {}
        self._route_cache: dict[tuple[str, tuple[float, float], tuple[float, float]], RouteResult] = {}
        self._surface_catalog: dict[str, list[RouteSpec]] = {mode: [] for mode in ("walk", "bike", "car")}
        self._multimodal_catalog: dict[str, list[list[RouteSpec]]] = {}

    def router(self, mode: str) -> LocalRouter:
        if mode not in self._routers:
            self._routers[mode] = LocalRouter(self.root / "reference_data" / "v2" / "graphs" / f"{mode}.graph.pkl.gz")
        return self._routers[mode]

    def surface(self, mode: str, rng: random.Random, start: tuple[float, float] | None = None, end: tuple[float, float] | None = None) -> RouteSpec:
        if start is None or end is None:
            catalog = self._surface_catalog[mode]
            if len(catalog) >= 12:
                return rng.choice(catalog)
            failures = 0
            for _ in range(80):
                a, b = rng.sample(self.bus_stops, 2)
                start, end = (a["lat"], a["lon"]), (b["lat"], b["lon"])
                if haversine_m(start, end) >= 700:
                    break
            while failures < 80:
                try:
                    result = self.router(mode).route(start, end, max_snap_distance_m=250.0, respect_restrictions=mode == "car")
                    geometry = list(result.geometry)
                    spec = RouteSpec(mode, geometry, {"route_reference": f"local_osm_{mode}_graph:{result.start_node}:{result.end_node}", "routing_profile": mode, "start_snap_distance_m": round(result.start_snap_distance_m, 3), "end_snap_distance_m": round(result.end_snap_distance_m, 3)}, [0.0, result.distance_m], result.distance_m)
                    catalog.append(spec)
                    return spec
                except ValueError:
                    failures += 1
                    a, b = rng.sample(self.bus_stops, 2)
                    start, end = (a["lat"], a["lon"]), (b["lat"], b["lon"])
                    if haversine_m(start, end) < 700:
                        continue
        key = (mode, tuple(start), tuple(end))
        result = self._route_cache.get(key)
        if result is None:
            result = self.router(mode).route(start, end, max_snap_distance_m=250.0, respect_restrictions=mode == "car")
            self._route_cache[key] = result
        geometry = list(result.geometry)
        return RouteSpec(mode, geometry, {"route_reference": f"local_osm_{mode}_graph:{result.start_node}:{result.end_node}", "routing_profile": mode, "start_snap_distance_m": round(result.start_snap_distance_m, 3), "end_snap_distance_m": round(result.end_snap_distance_m, 3)}, [0.0, result.distance_m], result.distance_m)

    def rail_spec(self, rng: random.Random, force_line5: bool = False, start_index: int | None = None, end_index: int | None = None, line: dict[str, Any] | None = None) -> RouteSpec:
        options = [item for item in self.rail if item["line_id"] == "5"] if force_line5 else self.rail
        line = line or rng.choice(options)
        stations = line["station_sequence"]
        indices = self._station_indices(line)
        if start_index is None:
            start_index = rng.randrange(0, len(stations) - 2)
        if end_index is None:
            end_index = rng.randint(start_index + 2, min(len(stations) - 1, start_index + 12))
        if end_index <= start_index or indices[end_index] <= indices[start_index]:
            raise ValueError("rail station subpath is not ordered")
        geometry = [tuple(point) for point in line["geometry"][indices[start_index] : indices[end_index] + 1]]
        if len(geometry) < 2 or geometry_distance(geometry) < 100:
            raise ValueError("rail geometry subpath is too short")
        offsets = self._offsets(geometry, len(stations[start_index : end_index + 1]))
        sequence = stations[start_index : end_index + 1]
        metadata = {"line": line["line_id"], "relation_id": line["relation_id"], "boarding_station": sequence[0]["name"], "alighting_station": sequence[-1]["name"], "station_sequence": [station["name"] for station in sequence], "rail_geometry_reference": f"osm_rail_relation_{line['relation_id']}", "routing_profile": "railway_relation_way_geometry"}
        return RouteSpec("rail", geometry, metadata, offsets, geometry_distance(geometry))

    def _station_indices(self, line: dict[str, Any]) -> list[int]:
        if line["relation_id"] in self._rail_indices:
            return self._rail_indices[line["relation_id"]]
        geometry = [tuple(point) for point in line["geometry"]]
        indices = []
        cursor = 0
        for station in line["station_sequence"]:
            index = min(range(cursor, len(geometry)), key=lambda i: haversine_m((station["lat"], station["lon"]), geometry[i]))
            indices.append(index)
            cursor = index
        self._rail_indices[line["relation_id"]] = indices
        return indices

    def bus_spec(self, rng: random.Random, start_index: int | None = None, end_index: int | None = None, route: dict[str, Any] | None = None) -> RouteSpec:
        route = route or rng.choice(self.bus)
        stops = route["stops"]
        if start_index is None:
            start_index = rng.randrange(0, len(stops) - 2)
        if end_index is None:
            end_index = rng.randint(start_index + 2, min(len(stops) - 1, start_index + 18))
        pair_geometry = route["pair_geometry"][start_index:end_index]
        if len(pair_geometry) != end_index - start_index or any(not pair["geometry"] for pair in pair_geometry):
            raise ValueError("bus pair geometry is incomplete")
        geometry: list[tuple[float, float]] = []
        offsets = [0.0]
        for pair in pair_geometry:
            segment = [tuple(point) for point in pair["geometry"]]
            if geometry and segment and geometry[-1] == segment[0]:
                segment = segment[1:]
            geometry.extend(segment)
            offsets.append(offsets[-1] + float(pair["distance_m"]))
        if len(geometry) < 2 or offsets[-1] < 100:
            raise ValueError("bus route subpath is too short")
        selected = stops[start_index : end_index + 1]
        metadata = {"route_id": route["route_id"], "route_uid": route["route_uid"], "direction": route.get("direction"), "boarding_stop": selected[0]["ars_id"], "alighting_stop": selected[-1]["ars_id"], "stop_sequence": [stop["ars_id"] for stop in selected], "route_geometry_reference": route["route_geometry_reference"], "routing_profile": route["routing_profile"]}
        return RouteSpec("bus", geometry, metadata, offsets, offsets[-1])

    def multimodal(self, rng: random.Random) -> list[RouteSpec]:
        kinds = ("walk_bus_walk", "walk_rail_walk", "walk_bus_rail_walk", "walk_rail_bus_walk", "walk_bus_bus_walk", "walk_rail_rail_walk")
        kind = rng.choice(kinds)
        if self._multimodal_catalog.get(kind):
            return rng.choice(self._multimodal_catalog[kind])
        for _ in range(100):
            try:
                if kind == "walk_bus_walk":
                    bus = self.bus_spec(rng)
                    before = self._nearby_point(rng, bus.geometry[0], 900, 2500)
                    after = self._nearby_point(rng, bus.geometry[-1], 900, 2500)
                    result = [self.surface("walk", rng, before, bus.geometry[0]), bus, self.surface("walk", rng, bus.geometry[-1], after)]
                    self._multimodal_catalog.setdefault(kind, []).append(result)
                    return result
                if kind == "walk_rail_walk":
                    rail = self.rail_spec(rng)
                    before = self._nearby_point(rng, rail.geometry[0], 900, 2500)
                    after = self._nearby_point(rng, rail.geometry[-1], 900, 2500)
                    result = [self.surface("walk", rng, before, rail.geometry[0]), rail, self.surface("walk", rng, rail.geometry[-1], after)]
                    self._multimodal_catalog.setdefault(kind, []).append(result)
                    return result
                if kind == "walk_bus_rail_walk":
                    route, stop_index, station, station_index = self._bus_rail_anchor(rng)
                    bus = self.bus_spec(rng, end_index=stop_index, route=route)
                    rail = self.rail_spec(rng, start_index=station_index, line=station)
                    before = self._nearby_point(rng, bus.geometry[0], 900, 2500)
                    after = self._nearby_point(rng, rail.geometry[-1], 900, 2500)
                    result = [self.surface("walk", rng, before, bus.geometry[0]), bus, rail, self.surface("walk", rng, rail.geometry[-1], after)]
                    self._multimodal_catalog.setdefault(kind, []).append(result)
                    return result
                if kind == "walk_rail_bus_walk":
                    route, stop_index, station, station_index = self._bus_rail_anchor(rng)
                    rail = self.rail_spec(rng, end_index=station_index, line=station)
                    bus = self.bus_spec(rng, start_index=stop_index, route=route)
                    before = self._nearby_point(rng, rail.geometry[0], 900, 2500)
                    after = self._nearby_point(rng, bus.geometry[-1], 900, 2500)
                    result = [self.surface("walk", rng, before, rail.geometry[0]), rail, bus, self.surface("walk", rng, bus.geometry[-1], after)]
                    self._multimodal_catalog.setdefault(kind, []).append(result)
                    return result
                if kind == "walk_bus_bus_walk":
                    first, second, first_index, second_index = self._bus_bus_anchor(rng)
                    left = self.bus_spec(rng, end_index=first_index, route=first)
                    right = self.bus_spec(rng, start_index=second_index, route=second)
                    before = self._nearby_point(rng, left.geometry[0], 900, 2500)
                    after = self._nearby_point(rng, right.geometry[-1], 900, 2500)
                    result = [self.surface("walk", rng, before, left.geometry[0]), left, right, self.surface("walk", rng, right.geometry[-1], after)]
                    self._multimodal_catalog.setdefault(kind, []).append(result)
                    return result
                if kind == "walk_rail_rail_walk":
                    station_name = rng.choice([station["name"] for line in self.rail for station in line["station_sequence"]])
                    options = [(line, index) for line in self.rail for index, station in enumerate(line["station_sequence"]) if station["name"] == station_name and index < len(line["station_sequence"]) - 2]
                    if len(options) < 2:
                        continue
                    first_line, first_index = rng.choice(options)
                    second_line, second_index = rng.choice(options)
                    first = self.rail_spec(rng, start_index=first_index, line=first_line)
                    second = self.rail_spec(rng, start_index=second_index, line=second_line)
                    before = self._nearby_point(rng, first.geometry[0], 900, 2500)
                    after = self._nearby_point(rng, second.geometry[-1], 900, 2500)
                    result = [self.surface("walk", rng, before, first.geometry[0]), first, second, self.surface("walk", rng, second.geometry[-1], after)]
                    self._multimodal_catalog.setdefault(kind, []).append(result)
                    return result
            except (ValueError, IndexError):
                continue
        raise ValueError("could not create a spatially connected multimodal route")

    def _nearby_point(self, rng: random.Random, target: tuple[float, float], minimum: float, maximum: float) -> tuple[float, float]:
        for _ in range(100):
            stop = rng.choice(self.bus_stops)
            point = (stop["lat"], stop["lon"])
            distance = haversine_m(point, target)
            if minimum <= distance <= maximum:
                return point
        raise ValueError("no nearby surface anchor")

    def _bus_rail_anchor(self, rng: random.Random) -> tuple[dict[str, Any], int, dict[str, Any], int]:
        candidates = []
        for route in self.bus:
            for index, stop in enumerate(route["stops"]):
                if index < 2 or index >= len(route["stops"]) - 2:
                    continue
                point = (stop["lat"], stop["lon"])
                for line in self.rail:
                    for station_index, station in enumerate(line["station_sequence"]):
                        if station_index < 2 or station_index >= len(line["station_sequence"]) - 2:
                            continue
                        distance = haversine_m(point, (station["lat"], station["lon"]))
                        if distance <= 150:
                            candidates.append((route, index, line, station_index))
        if not candidates:
            raise ValueError("no bus rail transfer anchor within 150m")
        return rng.choice(candidates)

    def _bus_bus_anchor(self, rng: random.Random) -> tuple[dict[str, Any], dict[str, Any], int, int]:
        candidates = []
        for first in self.bus:
            for first_index, first_stop in enumerate(first["stops"][2:-2], 2):
                for second in self.bus:
                    if first["route_uid"] == second["route_uid"]:
                        continue
                    for second_index, second_stop in enumerate(second["stops"][2:-2], 2):
                        if haversine_m((first_stop["lat"], first_stop["lon"]), (second_stop["lat"], second_stop["lon"])) <= 120:
                            candidates.append((first, second, first_index, second_index))
        if not candidates:
            raise ValueError("no bus bus transfer anchor")
        return rng.choice(candidates)

    @staticmethod
    def _offsets(geometry: list[tuple[float, float]], count: int) -> list[float]:
        total = geometry_distance(geometry)
        return [total * index / (count - 1) for index in range(count)]


def simulate_true(spec: RouteSpec, start: datetime, rng: random.Random, time_factor: float = 1.0) -> list[Point]:
    geometry = spec.geometry
    cumulative = [0.0]
    for first, second in zip(geometry, geometry[1:]):
        cumulative.append(cumulative[-1] + haversine_m(first, second))
    total = cumulative[-1]
    stop_offsets = sorted(set(max(0.0, min(total, value)) for value in spec.stop_offsets_m[1:-1]))
    boundaries = [0.0, *stop_offsets, total]
    points: list[Point] = []
    timestamp = start
    segment_id = 1
    for section_index, (section_start, section_end) in enumerate(zip(boundaries, boundaries[1:])):
        section_length = section_end - section_start
        if section_length <= 1:
            continue
        speed_factor = time_factor * rng.uniform(0.92, 1.08)
        base = BASE_SPEED[spec.mode] * speed_factor
        current = section_start
        if not points:
            location = point_at_distance(geometry, cumulative, current)
            points.append(Point(timestamp, location[0], location[1], 0.0, 0.0, segment_id, spec.mode))
        while current < section_end - 0.1:
            fraction = (current - section_start) / section_length
            ramp = min(1.0, fraction / 0.2, (1.0 - fraction) / 0.2) if spec.mode in {"rail", "bus", "car"} else 1.0
            speed = max(0.25 if spec.mode in {"car", "bus", "rail"} else 0.55, base * max(0.25, ramp))
            speed = min(MAX_SPEED[spec.mode], speed)
            dt = rng.uniform(4.8, 6.8)
            if (section_end - current) / speed < 2.5:
                break
            step = min(section_end - current, speed * dt)
            dt = max(0.25, step / speed)
            current += step
            timestamp += timedelta(seconds=dt)
            location = point_at_distance(geometry, cumulative, current)
            previous = (points[-1].lat, points[-1].lon)
            points.append(Point(timestamp, location[0], location[1], step / dt, bearing(previous, location), segment_id, spec.mode))
        if section_index < len(boundaries) - 2:
            dwell = rng.uniform(22, 58) if spec.mode == "rail" else rng.uniform(8, 34) if spec.mode == "bus" else rng.uniform(4, 12)
            elapsed = 0.0
            location = point_at_distance(geometry, cumulative, section_end)
            while elapsed < dwell:
                remaining = dwell - elapsed
                if remaining < 2.5:
                    timestamp += timedelta(seconds=remaining)
                    break
                dt = min(rng.uniform(4.8, 6.8), remaining)
                elapsed += dt
                timestamp += timedelta(seconds=dt)
                points.append(Point(timestamp, location[0], location[1], 0.0, points[-1].course_deg if points else 0.0, segment_id, spec.mode))
    if points[-1].lat != geometry[-1][0] or points[-1].lon != geometry[-1][1]:
        timestamp += timedelta(seconds=5)
        points.append(Point(timestamp, geometry[-1][0], geometry[-1][1], 0.0, points[-2].course_deg, segment_id, spec.mode))
    return points


def observe(points: list[Point], trip_id: str, device_id: str, profile_name: str, rng: random.Random) -> list[dict[str, Any]]:
    profile = NOISE[profile_name]
    output = []
    previous_time = None
    for index, point in enumerate(points):
        if index not in {0, len(points) - 1} and rng.random() < profile["missing"]:
            continue
        sigma = profile["sigma"]
        lat = point.lat + rng.gauss(0, sigma) / 111_320
        lon = point.lon + rng.gauss(0, sigma) / (111_320 * max(0.2, math.cos(math.radians(point.lat))))
        timestamp = point.timestamp + timedelta(seconds=rng.gauss(0, 0.12))
        if previous_time is not None and timestamp <= previous_time:
            timestamp = previous_time + timedelta(milliseconds=100)
        previous_time = timestamp
        accuracy = rng.uniform(*profile["accuracy"])
        reported_speed = min(35.0, max(0.0, point.speed_mps + rng.gauss(0, profile["speed_sigma"])))
        output.append({"schema_version": "2.0", "trip_id": trip_id, "device_id": device_id, "sequence": len(output), "timestamp": timestamp.isoformat().replace("+09:00", "+09:00"), "latitude": round(lat, 7), "longitude": round(lon, 7), "horizontal_accuracy_m": round(accuracy, 2), "altitude_m": round(point.altitude_m + rng.gauss(0, 2.0), 2), "vertical_accuracy_m": round(max(1.0, accuracy * rng.uniform(0.8, 1.4)), 2), "speed_mps": round(reported_speed, 3), "course_deg": round((point.course_deg + rng.gauss(0, profile["course_sigma"])) % 360, 2)})
    return output


class DatasetGeneratorV2:
    def __init__(self, root: Path, seed: int) -> None:
        self.root = root
        self.seed = seed
        self.reference = ReferenceV2(root)

    def generate_journey(self, number: int, category: str, rng: random.Random, force_line5: bool = False) -> Journey:
        noise_profile = rng.choice(tuple(NOISE))
        start = datetime(2026, 3, 1, rng.randint(6, 21), rng.randint(0, 59), rng.randint(0, 59), tzinfo=UTC9) + timedelta(days=rng.randint(0, 6))
        if category == "multimodal":
            specs = self.reference.multimodal(rng)
        else:
            spec = self.reference.rail_spec(rng, force_line5=force_line5) if category == "rail" else self.reference.bus_spec(rng) if category == "bus" else self.reference.surface(category, rng)
            specs = [spec]
        segments = []
        all_points: list[Point] = []
        timestamp = start
        for segment_id, spec in enumerate(specs, 1):
            points = simulate_true(spec, timestamp, rng, rng.uniform(0.82, 1.08))
            for point in points:
                point.segment_id = segment_id
            metadata = dict(spec.metadata)
            metadata["geometry_validation"] = geometry_metrics(points, spec.geometry)
            segment = Segment(segment_id, spec.mode, points[0].timestamp, points[-1].timestamp, points, metadata)
            segments.append(segment)
            all_points.extend(points if not all_points else points[1:])
            timestamp = points[-1].timestamp
        journey = Journey(f"trip_{number:06d}", f"device_{number % 31 + 1:03d}", category, segments[0].start_timestamp, segments[-1].end_timestamp, segments, all_points, noise_profile)
        return journey

    def generate(self, output_dir: Path, counts: dict[str, int], force_line5: int = 0) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name in ("gps", "ground_truth", "true_trajectories", "manifests", "validation", "visualizations"):
            (output_dir / name).mkdir(exist_ok=True)
        rows = []
        generated = 0
        for category in ("walk", "bike", "car", "bus", "rail", "multimodal"):
            for offset in range(counts.get(category, 0)):
                journey_rng = random.Random(self.seed + generated * 1_000_003)
                journey = self.generate_journey(generated + 1, category, journey_rng, category == "rail" and offset < force_line5)
                validation = validate_journey(journey)
                if validation["status"] != "PASS":
                    raise RuntimeError(f"v2 candidate failed before write: {journey.trip_id}: {validation}")
                gps = observe(journey.true_points, journey.trip_id, journey.device_id, journey.noise_profile, journey_rng)
                _write_csv(output_dir / "gps" / f"{journey.trip_id}.csv", GPS_COLUMNS, gps)
                _write_gt(output_dir / "ground_truth" / f"{journey.trip_id}.json", journey, validation)
                (output_dir / "true_trajectories" / f"{journey.trip_id}.json").write_text(json.dumps({"trip_id": journey.trip_id, "points": [{"timestamp": point.timestamp.isoformat(), "lat": point.lat, "lon": point.lon, "speed_mps": point.speed_mps, "segment_id": point.segment_id, "mode": point.mode} for point in journey.true_points]}, ensure_ascii=False), encoding="utf-8")
                rows.append({"trip_id": journey.trip_id, "scenario_category": category, "start_timestamp": journey.start_timestamp.isoformat(), "end_timestamp": journey.end_timestamp.isoformat(), "duration_seconds": int((journey.end_timestamp - journey.start_timestamp).total_seconds()), "distance_m": round(journey.distance_m, 3), "segment_count": len(journey.segments), "noise_profile": journey.noise_profile, "validation_status": "PASS"})
                generated += 1
        _write_csv(output_dir / "manifests" / "journey_manifest.csv", list(rows[0]), rows)
        manifest = {"dataset_version": "evaluation_dataset_v2", "generator_version": "2.0.0", "seed": self.seed, "journey_count": generated, "counts": counts, "gps_event_count": sum(1 for _ in output_dir.joinpath("gps").glob("*.csv") for __ in _read_rows(output_dir / "gps" / _.name)), "status": "candidate_validated"}
        (output_dir / "manifests" / "dataset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest


def validate_journey(journey: Journey) -> dict[str, Any]:
    checks = []
    true = journey.true_points
    timestamps = [point.timestamp for point in true]
    checks.append(("timestamp_reversal", timestamps == sorted(timestamps)))
    checks.append(("duplicate_timestamp", len(timestamps) == len(set(timestamps))))
    checks.append(("nonempty", bool(true)))
    speeds = []
    teleports = 0
    for first, second in zip(true, true[1:]):
        seconds = (second.timestamp - first.timestamp).total_seconds()
        distance = haversine_m((first.lat, first.lon), (second.lat, second.lon))
        if seconds <= 0 and distance > 0:
            teleports += 1
        if seconds > 0:
            speeds.append(distance / seconds)
            if distance / seconds > 100:
                teleports += 1
    checks.append(("zero_time_movement", teleports == 0))
    checks.append(("teleport", teleports == 0))
    checks.append(("speed_threshold", max(speeds, default=0) <= 35))
    checks.append(("reference_geometry_validation", all(segment.metadata.get("geometry_validation", {}).get("status") == "PASS" for segment in journey.segments)))
    transfers = []
    for first, second in zip(journey.segments, journey.segments[1:]):
        distance = haversine_m((first.points[-1].lat, first.points[-1].lon), (second.points[0].lat, second.points[0].lon))
        transfer = {"from_mode": first.mode, "to_mode": second.mode, "previous_end": [first.points[-1].lat, first.points[-1].lon], "next_start": [second.points[0].lat, second.points[0].lon], "transfer_distance_m": round(distance, 3), "transfer_location": [round((first.points[-1].lat + second.points[0].lat) / 2, 7), round((first.points[-1].lon + second.points[0].lon) / 2, 7)], "validity": "PASS" if distance <= 450 else "FAIL"}
        transfers.append(transfer)
    checks.append(("transfer_validation", all(item["validity"] == "PASS" for item in transfers)))
    return {"status": "PASS" if all(value for _name, value in checks) else "FAIL", "checks": {name: "PASS" if value else "FAIL" for name, value in checks}, "transfers": transfers, "max_true_speed_mps": round(max(speeds, default=0), 3)}


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_gt(path: Path, journey: Journey, validation: dict[str, Any]) -> None:
    payload = {"trip_id": journey.trip_id, "scenario_category": journey.scenario_category, "start_time": journey.start_timestamp.isoformat(), "end_time": journey.end_timestamp.isoformat(), "post_generation_validation": validation, "segments": []}
    for segment in journey.segments:
        item = {"trip_id": journey.trip_id, "segment_id": segment.segment_id, "mode": segment.mode, "start_time": segment.start_timestamp.isoformat(), "end_time": segment.end_timestamp.isoformat()}
        item.update(segment.metadata)
        payload["segments"].append(item)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
