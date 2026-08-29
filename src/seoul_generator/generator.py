from __future__ import annotations

import csv
import json
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import config_hash
from .gps import GPS_COLUMNS, observe
from .models import Journey, Segment
from .mobility import generate_segment_points
from .reference import ReferenceNetwork
from .routing import Router
from .visualization import write_visualization

PATTERNS = [
    ("walk", "rail", "walk"),
    ("walk", "bus", "walk"),
    ("walk", "bike", "walk"),
    ("walk", "car", "walk"),
    ("walk", "bus", "rail", "walk"),
    ("walk", "rail", "bus", "walk"),
    ("walk", "bike", "rail", "walk"),
    ("walk", "bus", "rail", "bus", "walk"),
]
HARD_CASES = [
    ("car_vs_bike", "congested_car", "car"),
    ("car_vs_bike", "fast_bike", "bike"),
    ("car_vs_bike", "parallel_road_and_bikeway", "car"),
    ("car_vs_bus", "stop_like_car", "car"),
    ("car_vs_bus", "slow_bus", "bus"),
    ("car_vs_bus", "long_stop_spacing", "bus"),
    ("walk_vs_bike", "slow_bike", "bike"),
    ("walk_vs_bike", "fast_walk", "walk"),
    ("walk_vs_bike", "walking_bike", "bike"),
    ("transit_false_positive", "car_near_station", "car"),
    ("transit_false_positive", "walk_near_station", "walk"),
    ("transit_false_positive", "parallel_rail_road", "car"),
    ("transit_false_positive", "parallel_rail_bus", "bus"),
    ("transit_false_positive", "car_past_bus_stops", "car"),
    ("transit_false_positive", "car_waiting_near_stop", "car"),
    ("transit_sequence", "station_proximity_only", "walk"),
    ("transit_sequence", "two_station_proximity", "car"),
    ("transit_sequence", "correct_line_sequence", "rail"),
    ("transit_sequence", "transfer_area_no_transfer", "walk"),
    ("transit_sequence", "real_transfer", "multimodal"),
]


class DatasetGenerator:
    def __init__(self, config: dict[str, Any], network: ReferenceNetwork):
        self.config = config
        self.network = network
        self.router = Router(network)
        self.seed = int(config["generator"]["seed"])
        self.interval = int(config["generator"]["sampling_interval_seconds"])
        self.noise_profiles = config["noise"]["profiles"]
        self.time_profiles = config["scenarios"]["time_profiles"]

    def generate_dataset(self, output_dir: Path, counts: dict[str, int], hard_case_count: int = 0) -> dict[str, Any]:
        for folder in (output_dir / "gps", output_dir / "ground_truth", output_dir / "manifests"):
            folder.mkdir(parents=True, exist_ok=True)
        manifest_rows = []
        segment_mode_counts: Counter[str] = Counter()
        hard_counts: Counter[str] = Counter()
        noise_counts: Counter[str] = Counter()
        samples: dict[str, tuple[Journey, list[dict]]] = {}
        total_events = 0
        trip_number = 1
        for category, count in counts.items():
            if category.startswith("poc_"):
                continue
            for offset in range(count):
                rng = random.Random(self.seed + trip_number * 1_000_003)
                hard_case = self._hard_case_for(category, offset, hard_case_count)
                journey = self.generate_journey(category, trip_number, rng, hard_case)
                events = observe(journey.true_points, journey.trip_id, journey.device_id, self.noise_profiles[journey.noise_profile], rng)
                samples.setdefault(category, (journey, events))
                if journey.hard_case_type:
                    samples.setdefault(f"hard:{journey.hard_case_type}", (journey, events))
                self._write_gps(output_dir / "gps" / f"{journey.trip_id}.csv", events)
                self._write_ground_truth(output_dir / "ground_truth" / f"{journey.trip_id}.json", journey)
                manifest_rows.append(self._manifest_row(journey))
                segment_mode_counts.update(segment.mode for segment in journey.segments)
                if hard_case:
                    hard_counts[hard_case[1]] += 1
                noise_counts[journey.noise_profile] += 1
                total_events += len(events)
                trip_number += 1
        journey_manifest_path = output_dir / "manifests" / "journey_manifest.csv"
        self._write_journey_manifest(journey_manifest_path, manifest_rows)
        dataset_manifest = {
            "dataset_version": self.config["generator"]["dataset_version"],
            "generator_version": self.config["generator"]["generator_version"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "seed": self.seed,
            "reference_data_versions": ["OSM snapshot at preparation time"],
            "sampling_interval": self.interval,
            "noise_profiles": dict(noise_counts),
            "journey_count": len(manifest_rows),
            "mode_journey_counts": {category: count for category, count in counts.items() if not category.startswith("poc_")},
            "multimodal_count": counts.get("multimodal", 0),
            "segment_mode_counts": dict(segment_mode_counts),
            "gps_event_count": total_events,
            "hard_case_counts": dict(hard_counts),
            "config_hash": config_hash(self.config),
        }
        (output_dir / "manifests" / "dataset_manifest.json").write_text(json.dumps(dataset_manifest, indent=2), encoding="utf-8")
        if samples:
            write_visualization(output_dir, samples)
        return dataset_manifest

    def generate_journey(self, category: str, number: int, rng: random.Random, hard_case: tuple[str, str, str] | None = None) -> Journey:
        start = self._start_time(rng)
        noise_profile = rng.choices(["clean", "normal", "noisy"], weights=[0.2, 0.6, 0.2])[0]
        if category == "multimodal":
            return self._multimodal(number, start, rng, noise_profile, hard_case)
        route, metadata = self._route(category, rng)
        time_factor = self._time_factor(start, rng)
        points = generate_segment_points(route, category, start, 1, rng, self.interval, time_factor, len(metadata.get("stop_sequence", [])) - 2, hard_case[1] if hard_case else None)
        segment = Segment(1, category, points[0].timestamp, points[-1].timestamp, points, metadata)
        return Journey(f"trip_{number:06d}", f"device_{number % 23 + 1:03d}", category, points[0].timestamp, points[-1].timestamp, [segment], points, noise_profile, hard_case[1] if hard_case else None, metadata.get("route_id"))

    def _multimodal(self, number: int, start: datetime, rng: random.Random, noise_profile: str, hard_case: tuple[str, str, str] | None) -> Journey:
        pattern = PATTERNS[rng.randrange(len(PATTERNS))]
        segments: list[Segment] = []
        all_points = []
        timestamp = start
        previous_end: list[float] | None = None
        for segment_id, mode in enumerate(pattern, 1):
            route, metadata = self._route(mode, rng)
            if previous_end is not None:
                route = _join_route(previous_end, route)
            points = generate_segment_points(route, mode, timestamp, segment_id, rng, self.interval, self._time_factor(timestamp, rng), len(metadata.get("stop_sequence", [])) - 2, None)
            segment = Segment(segment_id, mode, points[0].timestamp, points[-1].timestamp, points, metadata)
            segments.append(segment)
            all_points.extend(points if not all_points else points[1:])
            timestamp = points[-1].timestamp
            previous_end = route[-1]
        return Journey(f"trip_{number:06d}", f"device_{number % 23 + 1:03d}", "multimodal", segments[0].start_timestamp, segments[-1].end_timestamp, segments, all_points, noise_profile, hard_case[1] if hard_case else None)

    def _route(self, mode: str, rng: random.Random) -> tuple[list[list[float]], dict]:
        if mode in {"walk", "bike", "car"}:
            return self.router.surface_route(rng, mode)
        if mode == "bus":
            return self.router.bus_route(rng)
        return self.router.rail_route(rng)

    def _start_time(self, rng: random.Random) -> datetime:
        profile_name = sorted(self.time_profiles)[rng.randrange(len(self.time_profiles))]
        profile = self.time_profiles[profile_name]
        day = rng.randrange(7)
        hour = rng.randint(profile["start_hour"], max(profile["start_hour"], profile["end_hour"] - 1))
        minute = rng.randrange(0, 60)
        base = datetime.fromisoformat(self.config["generator"]["start_date"]).replace(tzinfo=timezone(timedelta(hours=9)))
        return base + timedelta(days=day, hours=hour, minutes=minute, seconds=rng.randrange(60))

    def _time_factor(self, timestamp: datetime, rng: random.Random) -> float:
        hour = timestamp.hour
        for profile in self.time_profiles.values():
            if profile["start_hour"] <= hour < profile["end_hour"]:
                return profile["speed_factor"] * rng.uniform(0.9, 1.1)
        return 1.0

    def _hard_case_for(self, category: str, offset: int, requested_count: int) -> tuple[str, str, str] | None:
        if requested_count <= 0 or offset % max(1, 100 // requested_count) != 0:
            return None
        candidates = [case for case in HARD_CASES if case[2] == category or (category == "multimodal" and case[2] == "multimodal")]
        return candidates[offset % len(candidates)] if candidates else None

    @staticmethod
    def _manifest_row(journey: Journey) -> dict[str, Any]:
        return {"trip_id": journey.trip_id, "scenario_category": journey.scenario_category, "start_timestamp": journey.start_timestamp.isoformat(), "end_timestamp": journey.end_timestamp.isoformat(), "duration_seconds": int((journey.end_timestamp - journey.start_timestamp).total_seconds()), "distance_m": round(journey.distance_m, 2), "segment_count": len(journey.segments), "noise_profile": journey.noise_profile, "hard_case_type": journey.hard_case_type or ""}

    @staticmethod
    def _write_gps(path: Path, events: list[dict]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=GPS_COLUMNS)
            writer.writeheader()
            writer.writerows(events)

    @staticmethod
    def _write_ground_truth(path: Path, journey: Journey) -> None:
        payload = {"trip_id": journey.trip_id, "scenario_category": journey.scenario_category, "start_timestamp": journey.start_timestamp.isoformat(), "end_timestamp": journey.end_timestamp.isoformat(), "segments": []}
        for segment in journey.segments:
            item = {"segment_id": segment.segment_id, "start_timestamp": segment.start_timestamp.isoformat(), "end_timestamp": segment.end_timestamp.isoformat(), "mode": segment.mode}
            item.update(segment.metadata)
            payload["segments"].append(item)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _write_journey_manifest(path: Path, rows: list[dict]) -> None:
        fields = ["trip_id", "scenario_category", "start_timestamp", "end_timestamp", "duration_seconds", "distance_m", "segment_count", "noise_profile", "hard_case_type"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def _join_route(previous_end: list[float], route: list[list[float]]) -> list[list[float]]:
    target = route[0]
    middle = [(previous_end[0] + target[0]) / 2, (previous_end[1] + target[1]) / 2]
    return [previous_end, [middle[0] + 0.0012, middle[1] - 0.0012], [middle[0] - 0.0012, middle[1] + 0.0012], target, *route[1:]]
