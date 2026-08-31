from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .v2_generator import DatasetGeneratorV2, ReferenceV2
from .v2_routing import haversine_m


class ReferenceV3(ReferenceV2):
    """v3 reference catalog: regional bus and car data, v2 foot/bike/rail data."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        reference = root / "reference_data" / "v3"
        data = json.loads((reference / "bus_network.json").read_text(encoding="utf-8"))
        self.bus = [item for item in data["routes"] if item["validation"]["status"] == "PASS" and len(item.get("pair_geometry", [])) == len(item.get("stops", [])) - 1 and all(pair.get("geometry") for pair in item.get("pair_geometry", []))]
        self.bus_stops = [stop for route in self.bus for stop in route["stops"]]
        self._bus_rail_candidates: list[tuple[dict, int, dict, int]] | None = None
        self._bus_bus_candidates: list[tuple[dict, dict, int, int]] | None = None

    def router(self, mode: str):
        return super().router(mode)

    @staticmethod
    def _cell(lat: float, lon: float) -> tuple[int, int]:
        return int(lat / 0.002), int(lon / 0.002)

    def _bus_rail_anchor(self, rng):
        if self._bus_rail_candidates is None:
            grid: dict[tuple[int, int], list[tuple[dict, int, dict]]] = {}
            for route in self.bus:
                for index, stop in enumerate(route["stops"]):
                    if 1 < index < len(route["stops"]) - 2:
                        grid.setdefault(self._cell(stop["lat"], stop["lon"]), []).append((route, index, stop))
            candidates = []
            for line in self.rail:
                for station_index, station in enumerate(line["station_sequence"]):
                    if 1 < station_index < len(line["station_sequence"]) - 2:
                        cell = self._cell(station["lat"], station["lon"])
                        for lat_cell in range(cell[0] - 1, cell[0] + 2):
                            for lon_cell in range(cell[1] - 1, cell[1] + 2):
                                for route, index, stop in grid.get((lat_cell, lon_cell), []):
                                    if haversine_m((stop["lat"], stop["lon"]), (station["lat"], station["lon"])) <= 150:
                                        candidates.append((route, index, line, station_index))
            self._bus_rail_candidates = candidates
        if not self._bus_rail_candidates:
            raise ValueError("no bus rail transfer anchor within 150m")
        return rng.choice(self._bus_rail_candidates)

    def _bus_bus_anchor(self, rng):
        if self._bus_bus_candidates is None:
            grid: dict[tuple[int, int], list[tuple[dict, int, dict]]] = {}
            for route in self.bus:
                for index, stop in enumerate(route["stops"]):
                    if 1 < index < len(route["stops"]) - 2:
                        grid.setdefault(self._cell(stop["lat"], stop["lon"]), []).append((route, index, stop))
            candidates = []
            for route in self.bus:
                for index, stop in enumerate(route["stops"]):
                    if not 1 < index < len(route["stops"]) - 2:
                        continue
                    cell = self._cell(stop["lat"], stop["lon"])
                    for lat_cell in range(cell[0] - 1, cell[0] + 2):
                        for lon_cell in range(cell[1] - 1, cell[1] + 2):
                            for other, other_index, other_stop in grid.get((lat_cell, lon_cell), []):
                                if route["route_uid"] != other["route_uid"] and haversine_m((stop["lat"], stop["lon"]), (other_stop["lat"], other_stop["lon"])) <= 120:
                                    candidates.append((route, other, index, other_index))
            self._bus_bus_candidates = candidates
        if not self._bus_bus_candidates:
            raise ValueError("no bus bus transfer anchor")
        return rng.choice(self._bus_bus_candidates)


class DatasetGeneratorV3(DatasetGeneratorV2):
    def __init__(self, root: Path, seed: int) -> None:
        self.root = root
        self.seed = seed
        self.reference = ReferenceV3(root)

    def generate(self, output_dir: Path, counts: dict[str, int], force_line5: int = 0) -> dict[str, Any]:
        manifest = super().generate(output_dir, counts, force_line5)
        manifest["dataset_version"] = "evaluation_dataset_v3"
        manifest["generator_version"] = "3.0.0"
        manifest["status"] = "candidate_validated"
        (output_dir / "manifests" / "dataset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest
