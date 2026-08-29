from __future__ import annotations

import math
from typing import Iterable

from .reference import ReferenceNetwork


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    value = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta = math.radians(lon2 - lon1)
    angle = math.degrees(math.atan2(math.sin(delta) * math.cos(phi2), math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta)))
    return (angle + 360.0) % 360.0


def polyline_distance(points: Iterable[list[float]]) -> float:
    values = list(points)
    return sum(haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(values, values[1:]))


def resample_polyline(polyline: list[list[float]], spacing_m: float = 35.0) -> list[list[float]]:
    if len(polyline) < 2:
        raise ValueError("a route needs at least two points")
    result = [polyline[0]]
    remaining = spacing_m
    for start, end in zip(polyline, polyline[1:]):
        length = haversine_m(start[0], start[1], end[0], end[1])
        if length == 0:
            continue
        while remaining <= length:
            ratio = remaining / length
            result.append([start[0] + ratio * (end[0] - start[0]), start[1] + ratio * (end[1] - start[1])])
            remaining += spacing_m
        remaining -= length
    if result[-1] != polyline[-1]:
        result.append(polyline[-1])
    return result


class Router:
    def __init__(self, network: ReferenceNetwork):
        self.network = network

    def surface_route(self, rng, preferred_mode: str) -> tuple[list[list[float]], dict]:
        corridors = self.network.surface_corridors
        if not corridors:
            raise ValueError("no OSM-derived surface corridors are available")
        corridor = corridors[rng.randrange(len(corridors))]
        geometry = corridor["geometry"] if rng.random() >= 0.5 else list(reversed(corridor["geometry"]))
        return resample_polyline(geometry, spacing_m=30.0), {"corridor_id": corridor["corridor_id"], "source": corridor["source"], "mode": preferred_mode}

    def rail_route(self, rng) -> tuple[list[list[float]], dict]:
        line_id = sorted(self.network.stations_by_line)[rng.randrange(len(self.network.stations_by_line))]
        stations = self.network.line(line_id)
        start = rng.randrange(0, len(stations) - 1)
        end = rng.randrange(start + 1, len(stations))
        selected = stations[start : end + 1]
        geometry = [[station["lat"], station["lon"]] for station in selected]
        return resample_polyline(geometry, spacing_m=55.0), {"line": line_id, "station_sequence": [station["name"] for station in selected]}

    def bus_route(self, rng) -> tuple[list[list[float]], dict]:
        route = self.network.bus_routes[rng.randrange(len(self.network.bus_routes))]
        stops = route["stops"]
        start = rng.randrange(0, len(stops) - 1)
        end = rng.randrange(start + 1, len(stops))
        selected = stops[start : end + 1]
        geometry = [[stop["lat"], stop["lon"]] for stop in selected]
        return resample_polyline(geometry, spacing_m=40.0), {"route_id": route["route_id"], "route_name": route["route_name"], "stop_sequence": [stop["name"] for stop in selected]}

