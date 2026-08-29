from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

MODES = ("walk", "bike", "car", "bus", "rail")


@dataclass
class Point:
    timestamp: datetime
    lat: float
    lon: float
    speed_mps: float
    course_deg: float
    segment_id: int
    mode: str
    altitude_m: float = 35.0


@dataclass
class Segment:
    segment_id: int
    mode: str
    start_timestamp: datetime
    end_timestamp: datetime
    points: list[Point]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Journey:
    trip_id: str
    device_id: str
    scenario_category: str
    start_timestamp: datetime
    end_timestamp: datetime
    segments: list[Segment]
    true_points: list[Point]
    noise_profile: str
    hard_case_type: str | None = None
    route_id: str | None = None

    @property
    def distance_m(self) -> float:
        from .routing import haversine_m

        return sum(haversine_m(a.lat, a.lon, b.lat, b.lon) for a, b in zip(self.true_points, self.true_points[1:]))

