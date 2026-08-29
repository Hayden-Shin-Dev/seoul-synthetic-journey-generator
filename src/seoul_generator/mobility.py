from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from .models import MODES, Point
from .routing import bearing_deg, haversine_m, polyline_distance

BASE_SPEEDS = {"walk": 1.35, "bike": 4.8, "car": 9.0, "bus": 7.5, "rail": 13.5}
SPEED_RANGES = {"walk": (0.65, 2.2), "bike": (1.0, 9.5), "car": (0.2, 22.0), "bus": (0.0, 17.0), "rail": (0.0, 25.0)}


def generate_segment_points(route: list[list[float]], mode: str, start: datetime, segment_id: int, rng: random.Random, sampling_interval: int, time_factor: float = 1.0, stop_count: int = 0, hard_case: str | None = None) -> list[Point]:
    if mode not in MODES:
        raise ValueError(f"unsupported mode: {mode}")
    if len(route) < 2:
        raise ValueError("route needs at least two coordinates")
    cumulative = [0.0]
    for first, second in zip(route, route[1:]):
        cumulative.append(cumulative[-1] + haversine_m(first[0], first[1], second[0], second[1]))
    total = cumulative[-1]
    if total <= 0:
        raise ValueError("route cannot have zero distance")
    stop_positions = _stop_positions(total, stop_count) if mode in {"bus", "rail"} else []
    points: list[Point] = []
    timestamp = start
    distance = 0.0
    previous_speed = 0.0
    stop_index = 0
    stop_remaining = 0
    while distance < total:
        if stop_index < len(stop_positions) and distance >= stop_positions[stop_index]:
            stop_remaining = rng.randint(8, 38) if mode == "bus" else rng.randint(22, 76)
            stop_index += 1
        at_stop = stop_remaining > 0
        if at_stop:
            speed = 0.0
            stop_remaining -= sampling_interval
        else:
            phase = distance / total
            speed = _speed(mode, phase, rng, time_factor, hard_case, previous_speed)
            previous_speed = speed
        location = _point_at_distance(route, cumulative, distance)
        next_distance = min(total, distance + speed * sampling_interval)
        next_location = _point_at_distance(route, cumulative, next_distance)
        course = bearing_deg(location[0], location[1], next_location[0], next_location[1]) if next_distance > distance else (points[-1].course_deg if points else 0.0)
        points.append(Point(timestamp, location[0], location[1], speed, course, segment_id, mode))
        timestamp += timedelta(seconds=sampling_interval)
        if at_stop:
            distance = min(total, distance + 0.01)
        else:
            distance = next_distance
    final = _point_at_distance(route, cumulative, total)
    points.append(Point(timestamp, final[0], final[1], 0.0, points[-1].course_deg if points else 0.0, segment_id, mode))
    return points


def _speed(mode: str, phase: float, rng: random.Random, time_factor: float, hard_case: str | None, previous: float) -> float:
    base = BASE_SPEEDS[mode] * time_factor
    if hard_case in {"congested_car", "stop_like_car"} and mode == "car":
        base *= 0.48
    elif hard_case == "fast_bike" and mode == "bike":
        base *= 1.45
    elif hard_case == "slow_bike" and mode == "bike":
        base *= 0.42
    elif hard_case == "fast_walk" and mode == "walk":
        base *= 1.35
    elif hard_case == "walking_bike" and mode == "bike":
        base *= 0.28
    elif hard_case == "slow_bus" and mode == "bus":
        base *= 0.55
    wave = 0.72 + 0.22 * math.sin(phase * math.pi * 4 + rng.random() * 0.8) + rng.uniform(-0.16, 0.16)
    if mode == "car" and phase < 0.12 or phase > 0.88:
        wave *= 0.7
    if mode == "rail":
        wave = 0.4 + 0.65 * math.sin(phase * math.pi) + rng.uniform(-0.08, 0.08)
    value = max(0.0, base * wave)
    low, high = SPEED_RANGES[mode]
    if mode == "car" and rng.random() < 0.04:
        value = 0.0
    if mode == "bus" and rng.random() < 0.06:
        value = 0.0
    if previous and value > previous * 1.5:
        value = previous * 1.5
    return max(low, min(high, value))


def _stop_positions(total: float, stop_count: int) -> list[float]:
    if stop_count <= 0:
        return []
    return [total * index / (stop_count + 1) for index in range(1, stop_count + 1)]


def _point_at_distance(route: list[list[float]], cumulative: list[float], distance: float) -> list[float]:
    index = min(len(route) - 2, max(0, _bisect(cumulative, distance) - 1))
    first, second = route[index], route[index + 1]
    span = cumulative[index + 1] - cumulative[index]
    ratio = 0.0 if span == 0 else (distance - cumulative[index]) / span
    return [first[0] + ratio * (second[0] - first[0]), first[1] + ratio * (second[1] - first[1])]


def _bisect(values: list[float], target: float) -> int:
    low, high = 0, len(values)
    while low < high:
        middle = (low + high) // 2
        if values[middle] <= target:
            low = middle + 1
        else:
            high = middle
    return low

