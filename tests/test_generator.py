from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from seoul_generator.config import load_config
from seoul_generator.generator import DatasetGenerator
from seoul_generator.gps import GPS_COLUMNS, observe
from seoul_generator.reference import ReferenceNetwork
from seoul_generator.validation import validate_dataset


ROOT = Path(__file__).resolve().parents[1]


def make_generator() -> DatasetGenerator:
    return DatasetGenerator(load_config(ROOT / "config"), ReferenceNetwork(ROOT / "reference_data" / "processed" / "seoul_network.json"))


def test_reference_data_loading_and_routing() -> None:
    generator = make_generator()
    assert len(generator.network.all_stations()) >= 30
    assert len(generator.network.surface_corridors) >= 10
    assert len(generator.network.bus_routes) >= 5
    for mode in ("walk", "bike", "car", "bus", "rail"):
        journey = generator.generate_journey(mode, 1, random.Random(101))
        assert journey.segments[0].mode == mode
        assert journey.distance_m > 100


def test_multimodal_has_real_segment_labels() -> None:
    journey = make_generator().generate_journey("multimodal", 1, random.Random(2026))
    assert len(journey.segments) >= 3
    assert all(segment.mode in {"walk", "bike", "car", "bus", "rail"} for segment in journey.segments)
    assert journey.scenario_category == "multimodal"


def test_gps_schema_noise_and_ground_truth_separation() -> None:
    journey = make_generator().generate_journey("car", 1, random.Random(5))
    events = observe(journey.true_points, journey.trip_id, journey.device_id, load_config(ROOT / "config")["noise"]["profiles"]["noisy"], random.Random(6))
    assert events
    assert list(events[0]) == GPS_COLUMNS
    assert not set(events[0]) & {"mode", "label", "route", "line", "station", "stop", "ground_truth", "scenario", "synthetic"}
    assert any(event["latitude"] != point.lat or event["longitude"] != point.lon for event, point in zip(events, journey.true_points))


def test_seed_reproducibility() -> None:
    generator = make_generator()
    first = generator.generate_journey("bike", 1, random.Random(777))
    second = generator.generate_journey("bike", 1, random.Random(777))
    assert [(point.timestamp, point.lat, point.lon, point.speed_mps) for point in first.true_points] == [(point.timestamp, point.lat, point.lon, point.speed_mps) for point in second.true_points]


def test_manifest_and_validation(tmp_path: Path) -> None:
    generator = make_generator()
    output = tmp_path / "dataset"
    manifest = generator.generate_dataset(output, {"walk": 1, "bike": 1, "car": 1, "bus": 1, "rail": 1, "multimodal": 1}, hard_case_count=0)
    assert manifest["journey_count"] == 6
    assert (output / "manifests" / "journey_manifest.csv").exists()
    report = validate_dataset(output)
    assert report["failed"] == 0
    with (output / "gps" / "trip_000001.csv").open(encoding="utf-8", newline="") as handle:
        assert csv.DictReader(handle).fieldnames == GPS_COLUMNS
    ground_truth = json.loads((output / "ground_truth" / "trip_000001.json").read_text(encoding="utf-8"))
    assert ground_truth["segments"][0]["mode"] == "walk"

