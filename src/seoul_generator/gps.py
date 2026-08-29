from __future__ import annotations

import math
import random
from datetime import timedelta

from .models import Point

GPS_COLUMNS = ["schema_version", "trip_id", "device_id", "sequence", "timestamp", "latitude", "longitude", "horizontal_accuracy_m", "altitude_m", "vertical_accuracy_m", "speed_mps", "course_deg"]


def observe(true_points: list[Point], trip_id: str, device_id: str, profile: dict, rng: random.Random, schema_version: str = "1.0") -> list[dict]:
    if not true_points:
        return []
    observations = []
    previous_timestamp = true_points[0].timestamp
    drift_lat, drift_lon = 0.0, 0.0
    for index, point in enumerate(true_points):
        if index not in {0, len(true_points) - 1} and rng.random() < profile["missing_probability"]:
            continue
        latitude, longitude = _jitter(point, profile, rng, drift_lat, drift_lon)
        if point.speed_mps == 0:
            drift_lat += rng.gauss(0, profile["stationary_drift_m"] / 111_000)
            drift_lon += rng.gauss(0, profile["stationary_drift_m"] / (111_000 * max(0.1, math.cos(math.radians(point.lat)))))
        else:
            drift_lat, drift_lon = 0.0, 0.0
        if index == 0:
            observed_timestamp = point.timestamp
        else:
            jitter = rng.gauss(0, profile["interval_jitter_seconds"])
            observed_timestamp = max(previous_timestamp + timedelta(milliseconds=100), point.timestamp + timedelta(seconds=jitter))
        accuracy = rng.uniform(profile["accuracy_min_m"], profile["accuracy_max_m"])
        if rng.random() < profile["poor_accuracy_probability"]:
            accuracy *= rng.uniform(1.5, 2.8)
        observations.append({
            "schema_version": schema_version,
            "trip_id": trip_id,
            "device_id": device_id,
            "sequence": len(observations),
            "timestamp": observed_timestamp.isoformat().replace("+00:00", "Z"),
            "latitude": round(latitude, 7),
            "longitude": round(longitude, 7),
            "horizontal_accuracy_m": round(accuracy, 2),
            "altitude_m": round(point.altitude_m + rng.gauss(0, 2.5), 2),
            "vertical_accuracy_m": round(max(1.0, accuracy * rng.uniform(0.8, 1.5)), 2),
            "speed_mps": round(max(0.0, point.speed_mps + rng.gauss(0, profile["speed_sigma_mps"])), 3),
            "course_deg": round((point.course_deg + rng.gauss(0, profile["course_sigma_deg"])) % 360, 2),
        })
        previous_timestamp = observed_timestamp
    return observations


def _jitter(point: Point, profile: dict, rng: random.Random, drift_lat: float, drift_lon: float) -> tuple[float, float]:
    sigma = profile["coordinate_sigma_m"]
    lat_offset = rng.gauss(0, sigma) / 111_000 + drift_lat
    lon_offset = rng.gauss(0, sigma) / (111_000 * max(0.1, math.cos(math.radians(point.lat)))) + drift_lon
    return point.lat + lat_offset, point.lon + lon_offset

