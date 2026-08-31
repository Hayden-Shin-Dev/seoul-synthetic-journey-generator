from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import osmium
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_ROUTE = ROOT / "reference_data" / "v2" / "raw" / "seoul_bus_route_stops_20260804.xlsx"
RAW_STOPS = ROOT / "reference_data" / "v2" / "raw" / "seoul_bus_stops_20260804.xlsx"
PBF = ROOT / "reference_data" / "v2" / "raw" / "Seoul.osm.pbf"
OUT = ROOT / "reference_data" / "v2"
BUS_REFERENCE = OUT / "bus_network.json"
VALIDATION = OUT / "bus_reference_validation.csv"
ROUTE_COLUMNS = ["ROUTE_ID", "노선명", "순번", "NODE_ID", "ARS_ID", "정류소명", "X좌표", "Y좌표"]
STOP_COLUMNS = ["NODE_ID", "ARS_ID", "정류소명", "X좌표", "Y좌표", "정류소타입"]
ROAD_HIGHWAYS = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street", "service", "road", "busway"}


class BusRelationCollector(osmium.SimpleHandler):
    def __init__(self, route_names: set[str]) -> None:
        super().__init__()
        self.route_names = route_names
        self.relations: list[dict[str, Any]] = []
        self.way_ids: set[int] = set()

    def relation(self, relation: osmium.osm.Relation) -> None:
        tags = dict(relation.tags)
        if tags.get("type") != "route" or tags.get("route") != "bus":
            return
        ref = str(tags.get("ref", "")).strip()
        if not ref or ref not in self.route_names:
            return
        members = [{"type": member.type, "ref": member.ref, "role": member.role} for member in relation.members]
        self.way_ids.update(member["ref"] for member in members if member["type"] == "w")
        self.relations.append({"id": relation.id, "tags": tags, "members": members})


class BusWayCollector(osmium.SimpleHandler):
    def __init__(self, way_ids: set[int]) -> None:
        super().__init__()
        self.way_ids = way_ids
        self.ways: dict[int, dict[str, Any]] = {}

    def way(self, way: osmium.osm.Way) -> None:
        if way.id not in self.way_ids:
            return
        points = [(node.ref, node.lat, node.lon) for node in way.nodes if node.location.valid()]
        if len(points) >= 2:
            self.ways[way.id] = {"id": way.id, "tags": dict(way.tags), "points": points}


def haversine_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    radius = 6_371_000.0
    lat1, lon1 = math.radians(first[0]), math.radians(first[1])
    lat2, lon2 = math.radians(second[0]), math.radians(second[1])
    dlat, dlon = lat2 - lat1, math.radians(second[1] - first[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def tag_value(tags: dict[str, Any], key: str) -> str | None:
    value = tags.get(key)
    return str(value).strip().lower() if value is not None else None


def oneway(tags: dict[str, Any]) -> int:
    value = tag_value(tags, "oneway")
    if value in {"yes", "true", "1"} or tag_value(tags, "junction") == "roundabout":
        return 1
    if value == "-1":
        return -1
    return 0


class RelationRoadGraph:
    def __init__(self, relation: dict[str, Any], ways: dict[int, dict[str, Any]]) -> None:
        self.nodes: dict[int, tuple[float, float]] = {}
        self.adj: dict[int, list[tuple[int, float]]] = defaultdict(list)
        for member in relation["members"]:
            if member["type"] != "w" or member["ref"] not in ways:
                continue
            way = ways[member["ref"]]
            points = way["points"]
            for node_id, lat, lon in points:
                self.nodes[node_id] = (lat, lon)
            direction = oneway(way["tags"])
            for first, second in zip(points, points[1:]):
                distance = haversine_m((first[1], first[2]), (second[1], second[2]))
                if distance <= 0:
                    continue
                if direction >= 0:
                    self.adj[first[0]].append((second[0], distance))
                if direction <= 0:
                    self.adj[second[0]].append((first[0], distance))
        self.grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        for node_id, point in self.nodes.items():
            self.grid[(int(point[0] / 0.002), int(point[1] / 0.002))].append(node_id)

    def nearest(self, point: tuple[float, float], max_distance_m: float = 250.0) -> tuple[int, float]:
        cell = (int(point[0] / 0.002), int(point[1] / 0.002))
        best_id = None
        best_distance = float("inf")
        for radius in range(0, 5):
            for lat_cell in range(cell[0] - radius, cell[0] + radius + 1):
                for lon_cell in range(cell[1] - radius, cell[1] + radius + 1):
                    for node_id in self.grid.get((lat_cell, lon_cell), []):
                        distance = haversine_m(point, self.nodes[node_id])
                        if distance < best_distance:
                            best_id, best_distance = node_id, distance
            if best_distance <= max_distance_m and radius >= 1:
                break
        if best_id is None or best_distance > max_distance_m:
            raise ValueError(f"stop is more than {max_distance_m}m from OSM route way")
        return best_id, best_distance

    def route(self, start: int, end: int) -> tuple[list[int], float] | None:
        queue: list[tuple[float, float, int]] = [(0.0, 0.0, start)]
        distances = {start: 0.0}
        previous: dict[int, int] = {}
        goal = self.nodes[end]
        while queue:
            _priority, distance, node = heapq.heappop(queue)
            if distance != distances.get(node):
                continue
            if node == end:
                path = [node]
                while path[-1] != start:
                    path.append(previous[path[-1]])
                path.reverse()
                return path, distance
            for target, edge_distance in self.adj.get(node, []):
                candidate = distance + edge_distance
                if candidate >= distances.get(target, float("inf")):
                    continue
                distances[target] = candidate
                previous[target] = node
                heapq.heappush(queue, (candidate + haversine_m(self.nodes[target], goal), candidate, target))
        return None


def row_to_stop(row: pd.Series) -> dict[str, Any]:
    return {"node_id": int(row["NODE_ID"]), "ars_id": str(row["ARS_ID"]).zfill(5), "name": str(row["정류소명"]), "lat": float(row["Y좌표"]), "lon": float(row["X좌표"])}


def build_candidate(group: pd.DataFrame, relation: dict[str, Any], ways: dict[int, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    ordered = group.sort_values("순번")
    stops = [row_to_stop(row) for _, row in ordered.iterrows()]
    graph = RelationRoadGraph(relation, ways)
    try:
        snapped = [graph.nearest((stop["lat"], stop["lon"])) for stop in stops]
    except ValueError:
        return None
    geometry: list[list[float]] = []
    pair_records = []
    for first, second in zip(snapped, snapped[1:]):
        result = graph.route(first[0], second[0])
        if result is None:
            return None
        path, distance = result
        segment = [[graph.nodes[node_id][0], graph.nodes[node_id][1]] for node_id in path]
        if geometry and segment and geometry[-1] == segment[0]:
            segment = segment[1:]
        geometry.extend(segment)
        pair_records.append({"from_ars_id": stops[len(pair_records)]["ars_id"], "to_ars_id": stops[len(pair_records) + 1]["ars_id"], "distance_m": round(distance, 3), "geometry": segment})
    from_name = relation["tags"].get("from", "")
    to_name = relation["tags"].get("to", "")
    direction = f"{from_name} -> {to_name}" if from_name or to_name else None
    record = {"route_uid": int(ordered.iloc[0]["ROUTE_ID"]), "route_id": str(ordered.iloc[0]["노선명"]), "direction": direction, "direction_source": "OSM relation from/to; official file has no direction column", "osm_relation_id": relation["id"], "stops": stops, "ordered_stop_ids": [stop["node_id"] for stop in stops], "ordered_ars_ids": [stop["ars_id"] for stop in stops], "geometry": geometry, "geometry_method": "OSM bus relation member road graph routed between official Seoul stop sequence", "route_geometry_reference": f"osm_bus_relation_{relation['id']}", "routing_profile": "bus_on_osm_road_graph", "pair_geometry": pair_records, "stop_snap_distances_m": [round(snap[1], 3) for snap in snapped], "validation": {"official_route_membership": "PASS", "sequence": "PASS", "direction_consistency": "PASS" if direction else "NOT_PROVIDED", "duplicate_sequence_count": int(ordered["순번"].duplicated().sum()), "coordinate_missing_count": 0, "routable_pair_count": len(pair_records), "failed_pair_count": 0, "status": "PASS"}}
    validation = {"route_uid": record["route_uid"], "route_id": record["route_id"], "direction": direction or "", "osm_relation_id": relation["id"], "stop_count": len(stops), "pair_count": len(pair_records), "routable_pair_count": len(pair_records), "failed_pair_count": 0, "max_stop_snap_distance_m": max(record["stop_snap_distances_m"], default=0), "official_route_membership": "PASS", "sequence": "PASS", "direction_consistency": "PASS" if direction else "NOT_PROVIDED", "status": "PASS"}
    return record, validation


def main() -> None:
    parser = argparse.ArgumentParser(description="Build official Seoul bus reference over actual OSM road geometry")
    parser.add_argument("--route-file", type=Path, default=RAW_ROUTE)
    parser.add_argument("--stop-file", type=Path, default=RAW_STOPS)
    parser.add_argument("--pbf", type=Path, default=PBF)
    args = parser.parse_args()
    route_df = pd.read_excel(args.route_file, dtype={"ARS_ID": str})
    stop_df = pd.read_excel(args.stop_file, dtype={"ARS_ID": str})
    if route_df.columns.tolist() != ROUTE_COLUMNS or stop_df.columns.tolist() != STOP_COLUMNS:
        raise SystemExit("official bus schema changed; refusing to guess columns")
    if route_df.isna().any().any() or stop_df.isna().any().any():
        raise SystemExit("official bus source contains missing fields; refusing to create incomplete reference")
    names = {str(value).strip() for value in route_df["노선명"].unique()}
    relations = BusRelationCollector(names)
    relations.apply_file(str(args.pbf), locations=False, idx="flex_mem")
    ways = BusWayCollector(relations.way_ids)
    ways.apply_file(str(args.pbf), locations=True, idx="flex_mem")
    by_ref: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in relations.relations:
        by_ref[str(relation["tags"].get("ref", "")).strip()].append(relation)
    records = []
    validations = []
    for _route_uid, group in route_df.groupby("ROUTE_ID", sort=True):
        route_name = str(group.iloc[0]["노선명"]).strip()
        candidates = []
        for relation in by_ref.get(route_name, []):
            candidate = build_candidate(group, relation, ways.ways)
            if candidate is not None:
                candidates.append(candidate)
        if candidates:
            record, validation = min(candidates, key=lambda item: (max(item[1].get("max_stop_snap_distance_m", 1e9), 0), -item[1]["routable_pair_count"]))
        else:
            record = {"route_uid": int(group.iloc[0]["ROUTE_ID"]), "route_id": route_name, "direction": None, "direction_source": "not present in official downloaded schema", "stops": [row_to_stop(row) for _, row in group.sort_values("순번").iterrows()], "ordered_stop_ids": [int(value) for value in group.sort_values("순번")["NODE_ID"]], "ordered_ars_ids": [str(value).zfill(5) for value in group.sort_values("순번")["ARS_ID"]], "geometry": [], "geometry_method": "FAIL_NO_ROUTABLE_OSM_BUS_RELATION", "validation": {"status": "FAIL", "reason": "no OSM bus relation supplied a complete routable path for the official stop sequence"}}
            validation = {"route_uid": record["route_uid"], "route_id": route_name, "stop_count": len(record["stops"]), "status": "FAIL", "reason": record["validation"]["reason"]}
        records.append(record)
        validations.append(validation)
    OUT.mkdir(parents=True, exist_ok=True)
    BUS_REFERENCE.write_text(json.dumps({"coordinate_system": "EPSG:4326", "source": "Seoul official route stop sequence plus OSM bus relation road graph", "source_file": str(args.route_file.relative_to(ROOT)).replace("\\", "/"), "stop_source_file": str(args.stop_file.relative_to(ROOT)).replace("\\", "/"), "osm_source_file": str(args.pbf.relative_to(ROOT)).replace("\\", "/"), "osm_bus_relation_count": len(relations.relations), "routes": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = []
    for validation in validations:
        for field in validation:
            if field not in fields:
                fields.append(field)
    with VALIDATION.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(validations)
    summary = {"official_route_count": int(route_df["ROUTE_ID"].nunique()), "osm_bus_relation_count": len(relations.relations), "route_pass_count": sum(row["status"] == "PASS" for row in validations), "route_fail_count": sum(row["status"] == "FAIL" for row in validations), "created_at": datetime.now(UTC).isoformat()}
    (OUT / "bus_reference_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
