from __future__ import annotations

import gzip
import heapq
import math
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class RouteResult:
    mode: str
    start_node: int
    end_node: int
    node_ids: tuple[int, ...]
    geometry: tuple[tuple[float, float], ...]
    distance_m: float
    duration_s: float
    start_snap_distance_m: float
    end_snap_distance_m: float


def haversine_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    radius = 6_371_000.0
    lat1, lon1 = math.radians(first[0]), math.radians(first[1])
    lat2, lon2 = math.radians(second[0]), math.radians(second[1])
    dlat = lat2 - lat1
    dlon = math.radians(second[1] - first[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


class LocalRouter:
    def __init__(self, graph_path: Path, cell_size: float = 0.002) -> None:
        with gzip.open(graph_path, "rb") as handle:
            self.graph = pickle.load(handle)
        self.mode = self.graph["stats"]["mode"]
        self.nodes: dict[int, tuple[float, float]] = self.graph["nodes"]
        self.adjacency: dict[int, list[tuple[int, float, int, float]]] = self.graph["adj"]
        self.restrictions: set[tuple[int, int, int]] = {
            (item["from_way"], item["via_node"], item["to_way"])
            for item in self.graph.get("restrictions", [])
            if item.get("restriction", "").startswith("no_")
        }
        self.cell_size = cell_size
        self.grid: dict[tuple[int, int], list[int]] = {}
        for node_id, point in self.nodes.items():
            self.grid.setdefault(self._cell(point), []).append(node_id)

    def _cell(self, point: tuple[float, float]) -> tuple[int, int]:
        return int(point[0] / self.cell_size), int(point[1] / self.cell_size)

    def nearest_node(self, point: tuple[float, float], max_distance_m: float = 500.0) -> tuple[int, float]:
        return self.nearest_nodes(point, max_distance_m, 1)[0]

    def nearest_nodes(self, point: tuple[float, float], max_distance_m: float = 500.0, limit: int = 5) -> list[tuple[int, float]]:
        center = self._cell(point)
        candidates: list[tuple[float, int]] = []
        for radius in range(0, 8):
            for lat_cell in range(center[0] - radius, center[0] + radius + 1):
                for lon_cell in range(center[1] - radius, center[1] + radius + 1):
                    for node_id in self.grid.get((lat_cell, lon_cell), []):
                        distance = haversine_m(point, self.nodes[node_id])
                        if distance <= max_distance_m:
                            candidates.append((distance, node_id))
            if len(candidates) >= limit and radius >= 1:
                break
        candidates = sorted(set(candidates))[:limit]
        if not candidates:
            raise ValueError(f"no {self.mode} graph node within {max_distance_m}m of {point}")
        return [(node_id, distance) for distance, node_id in candidates]

    def route(self, start: tuple[float, float], end: tuple[float, float], max_snap_distance_m: float = 500.0, respect_restrictions: bool = True) -> RouteResult:
        start_candidates = self.nearest_nodes(start, max_snap_distance_m)
        end_candidates = self.nearest_nodes(end, max_snap_distance_m)
        best = None
        pairs = [(start_candidates[0], end_candidates[0])]
        pairs.extend((start_candidate, end_candidate) for start_candidate in start_candidates[1:] for end_candidate in end_candidates)
        for (start_id, start_snap), (end_id, end_snap) in pairs:
            if start_id == end_id:
                continue
            result = self._shortest_path(start_id, end_id, respect_restrictions)
            if result is not None:
                best = (result, start_id, end_id, start_snap, end_snap)
                break
        if best is None:
            for start_id, start_snap in start_candidates:
                for end_id, end_snap in end_candidates:
                    if start_id == end_id:
                        continue
                    result = self._shortest_path(start_id, end_id, respect_restrictions)
                    if result is not None and (best is None or result[1] < best[0][1]):
                        best = (result, start_id, end_id, start_snap, end_snap)
        if best is None:
            raise ValueError(f"no connected {self.mode} route from the candidate graph nodes")
        result, start_id, end_id, start_snap, end_snap = best
        node_ids, distance, duration = result
        return RouteResult(
            mode=self.mode,
            start_node=start_id,
            end_node=end_id,
            node_ids=tuple(node_ids),
            geometry=tuple(self.nodes[node_id] for node_id in node_ids),
            distance_m=distance,
            duration_s=duration,
            start_snap_distance_m=start_snap,
            end_snap_distance_m=end_snap,
        )

    def _shortest_path(self, start: int, end: int, respect_restrictions: bool) -> tuple[list[int], float, float] | None:
        goal = self.nodes[end]
        queue: list[tuple[float, float, int, int]] = [(0.0, 0.0, start, 0)]
        distances: dict[tuple[int, int], float] = {(start, 0): 0.0}
        durations: dict[tuple[int, int], float] = {(start, 0): 0.0}
        previous: dict[tuple[int, int], tuple[int, int]] = {}
        goal_state: tuple[int, int] | None = None
        while queue:
            _priority, distance, node, previous_way = heapq.heappop(queue)
            state = (node, previous_way)
            if distance != distances.get(state):
                continue
            if node == end:
                goal_state = state
                break
            for target, edge_distance, way_id, edge_speed in self.adjacency.get(node, []):
                if respect_restrictions and previous_way and (previous_way, node, way_id) in self.restrictions:
                    continue
                next_state = (target, way_id)
                candidate = distance + edge_distance
                if candidate >= distances.get(next_state, float("inf")):
                    continue
                distances[next_state] = candidate
                durations[next_state] = durations[state] + edge_distance / max(edge_speed, 0.1)
                previous[next_state] = state
                heuristic = haversine_m(self.nodes[target], goal)
                heapq.heappush(queue, (candidate + heuristic, candidate, target, way_id))
        if goal_state is None:
            return None
        states = [goal_state]
        while states[-1] != (start, 0):
            states.append(previous[states[-1]])
        states.reverse()
        return [node for node, _way in states], distances[goal_state], durations[goal_state]


def route_geometry_length(geometry: Iterable[tuple[float, float]]) -> float:
    points = list(geometry)
    return sum(haversine_m(first, second) for first, second in zip(points, points[1:]))
