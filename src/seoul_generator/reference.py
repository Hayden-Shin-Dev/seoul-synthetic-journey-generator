from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ReferenceNetwork:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        self._validate()

    @property
    def stations_by_line(self) -> dict[str, list[dict[str, Any]]]:
        return self.data["stations_by_line"]

    @property
    def bus_routes(self) -> list[dict[str, Any]]:
        return self.data["bus_routes"]

    @property
    def surface_corridors(self) -> list[dict[str, Any]]:
        return self.data.get("surface_corridors", [])

    def all_stations(self) -> list[dict[str, Any]]:
        unique: dict[int, dict[str, Any]] = {}
        for stations in self.stations_by_line.values():
            for station in stations:
                unique[station["osm_id"]] = station
        return list(unique.values())

    def line(self, line_id: str) -> list[dict[str, Any]]:
        return self.stations_by_line[line_id]

    def bus_route(self, route_id: str) -> dict[str, Any]:
        return next(route for route in self.bus_routes if route["route_id"] == route_id)

    def _validate(self) -> None:
        if self.data.get("coordinate_system") != "WGS84":
            raise ValueError("reference network must use WGS84")
        if not self.stations_by_line or not self.bus_routes:
            raise ValueError("reference network is empty")
        for line_id, stations in self.stations_by_line.items():
            if len(stations) < 2:
                raise ValueError(f"line has fewer than two stations: {line_id}")
            for station in stations:
                if not (-90 <= station["lat"] <= 90 and -180 <= station["lon"] <= 180):
                    raise ValueError(f"invalid station coordinates: {station}")
        for route in self.bus_routes:
            if len(route["stops"]) < 2:
                raise ValueError(f"bus route has fewer than two stops: {route['route_id']}")

