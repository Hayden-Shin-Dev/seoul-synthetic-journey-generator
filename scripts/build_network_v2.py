from __future__ import annotations

import argparse
import csv
import gzip
import heapq
import json
import math
import pickle
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import osmium


ROOT = Path(__file__).resolve().parents[1]
PBF = ROOT / "reference_data" / "v2" / "raw" / "Seoul.osm.pbf"
OUT = ROOT / "reference_data" / "v2"
GRAPH_DIR = OUT / "graphs"
RAIL_PATH = OUT / "rail_network.json"
RAIL_VALIDATION_PATH = OUT / "rail_reference_validation.csv"

RAIL_ROUTES = {"subway", "train", "light_rail", "railway"}
RAIL_WAY_TYPES = {"rail", "subway", "light_rail", "tram", "narrow_gauge"}
NON_ROUTABLE_HIGHWAYS = {"construction", "proposed", "raceway", "corridor", "platform", "services", "rest_area"}
CAR_HIGHWAYS = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service", "road", "busway",
}
WALK_HIGHWAYS = CAR_HIGHWAYS | {"footway", "pedestrian", "path", "steps", "track"}
BIKE_HIGHWAYS = CAR_HIGHWAYS | {"cycleway", "path", "track"}


def tag_value(tags: dict[str, str], key: str) -> str | None:
    value = tags.get(key)
    return str(value).strip().lower() if value is not None else None


def blocked(tags: dict[str, str], mode: str) -> bool:
    if tag_value(tags, "access") in {"no", "private"}:
        return True
    if mode == "car" and tag_value(tags, "motor_vehicle") in {"no", "private"}:
        return True
    if mode == "car" and tag_value(tags, "motorcar") in {"no", "private"}:
        return True
    if mode == "walk" and tag_value(tags, "foot") in {"no", "private"}:
        return True
    if mode == "bike" and tag_value(tags, "bicycle") in {"no", "private"}:
        return True
    return False


def allowed_way(tags: dict[str, str], mode: str) -> bool:
    highway = tag_value(tags, "highway")
    if not highway or highway in NON_ROUTABLE_HIGHWAYS or blocked(tags, mode):
        return False
    if mode == "car":
        return highway in CAR_HIGHWAYS
    if mode == "walk":
        if highway in {"motorway", "motorway_link", "trunk", "trunk_link"} and tag_value(tags, "foot") not in {"yes", "designated"}:
            return False
        return highway in WALK_HIGHWAYS or tag_value(tags, "foot") in {"yes", "designated"}
    if mode == "bike":
        if highway in {"motorway", "motorway_link"}:
            return False
        if highway in {"trunk", "trunk_link"} and tag_value(tags, "bicycle") not in {"yes", "designated"}:
            return False
        if highway in {"footway", "pedestrian", "steps"} and tag_value(tags, "bicycle") not in {"yes", "designated"}:
            return False
        return highway in BIKE_HIGHWAYS or tag_value(tags, "bicycle") in {"yes", "designated"}
    return False


def is_oneway(tags: dict[str, str], mode: str) -> int:
    if mode in {"walk", "bike"} and tag_value(tags, f"oneway:{mode}") in {"no", "false", "0"}:
        return 0
    value = tag_value(tags, "oneway")
    if value in {"yes", "true", "1"} or tag_value(tags, "junction") == "roundabout":
        return 1
    if value == "-1":
        return -1
    return 0


def speed_mps(tags: dict[str, str], mode: str) -> float:
    defaults = {"car": 11.1, "walk": 1.35, "bike": 4.8}
    raw = tag_value(tags, "maxspeed")
    if raw:
        number = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
        try:
            value = float(number)
            if "mph" in raw:
                value *= 0.44704
            else:
                value /= 3.6
            if value > 0:
                return min(value, 33.3 if mode == "car" else defaults[mode] * 2.5)
        except ValueError:
            pass
    return defaults[mode]


class RelationCollector(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.rail_relations: list[dict[str, Any]] = []
        self.rail_way_ids: set[int] = set()
        self.rail_node_ids: set[int] = set()
        self.restrictions: list[dict[str, Any]] = []

    def relation(self, relation: osmium.osm.Relation) -> None:
        tags = dict(relation.tags)
        if tags.get("type") == "route" and tags.get("route") in RAIL_ROUTES:
            members = []
            for member in relation.members:
                item = {"type": member.type, "ref": member.ref, "role": member.role}
                members.append(item)
                if member.type == "w":
                    self.rail_way_ids.add(member.ref)
                elif member.type == "n":
                    self.rail_node_ids.add(member.ref)
            self.rail_relations.append({"id": relation.id, "tags": tags, "members": members})
        if tags.get("type") == "restriction" and tags.get("restriction"):
            from_way = next((m.ref for m in relation.members if m.role == "from" and m.type == "w"), None)
            to_way = next((m.ref for m in relation.members if m.role == "to" and m.type == "w"), None)
            via_node = next((m.ref for m in relation.members if m.role == "via" and m.type == "n"), None)
            if from_way and to_way and via_node:
                self.restrictions.append({"id": relation.id, "from_way": from_way, "to_way": to_way, "via_node": via_node, "restriction": tags["restriction"]})


class NetworkCollector(osmium.SimpleHandler):
    def __init__(self, rail_way_ids: set[int], rail_node_ids: set[int]) -> None:
        super().__init__()
        self.rail_way_ids = rail_way_ids
        self.rail_node_ids = rail_node_ids
        self.rail_ways: dict[int, dict[str, Any]] = {}
        self.station_nodes: dict[int, dict[str, Any]] = {}
        self.graphs: dict[str, dict[str, Any]] = {
            mode: {"nodes": {}, "adj": defaultdict(list), "way_count": 0, "edge_count": 0}
            for mode in ("car", "walk", "bike")
        }

    def node(self, node: osmium.osm.Node) -> None:
        if node.id not in self.rail_node_ids or not node.location.valid():
            return
        self.station_nodes[node.id] = {"id": node.id, "lat": node.location.lat, "lon": node.location.lon, "tags": dict(node.tags)}

    def way(self, way: osmium.osm.Way) -> None:
        tags = dict(way.tags)
        points = [(node.ref, node.lat, node.lon) for node in way.nodes if node.location.valid()]
        if way.id in self.rail_way_ids and len(points) >= 2:
            self.rail_ways[way.id] = {"id": way.id, "tags": tags, "nodes": points}
        highway = tag_value(tags, "highway")
        if not highway or len(points) < 2:
            return
        for mode, graph in self.graphs.items():
            if not allowed_way(tags, mode):
                continue
            graph["way_count"] += 1
            direction = is_oneway(tags, mode)
            velocity = speed_mps(tags, mode)
            for node_id, lat, lon in points:
                graph["nodes"][node_id] = (lat, lon)
            for first, second in zip(points, points[1:]):
                distance = haversine(first[1], first[2], second[1], second[2])
                if distance <= 0:
                    continue
                if direction >= 0:
                    graph["adj"][first[0]].append((second[0], distance, way.id, velocity))
                    graph["edge_count"] += 1
                if direction <= 0:
                    graph["adj"][second[0]].append((first[0], distance, way.id, velocity))
                    graph["edge_count"] += 1


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def stitch_relation(relation: dict[str, Any], ways: dict[int, dict[str, Any]]) -> tuple[list[list[float]], int, int]:
    geometry: list[list[float]] = []
    missing = 0
    discontinuities = 0
    previous_node: int | None = None
    for member in relation["members"]:
        if member["type"] != "w":
            continue
        way = ways.get(member["ref"])
        if not way:
            missing += 1
            continue
        points = way["nodes"]
        if previous_node is not None:
            if points[0][0] == previous_node:
                pass
            elif points[-1][0] == previous_node:
                points = list(reversed(points))
            else:
                discontinuities += 1
        if not geometry:
            geometry.extend([[point[1], point[2]] for point in points])
        else:
            geometry.extend([[point[1], point[2]] for point in points if point[0] != previous_node])
        previous_node = points[-1][0]
    return geometry, missing, discontinuities


def relation_rail_graph(relation: dict[str, Any], ways: dict[int, dict[str, Any]]) -> tuple[dict[int, tuple[float, float]], dict[int, list[tuple[int, float]]], int]:
    nodes: dict[int, tuple[float, float]] = {}
    adjacency: dict[int, list[tuple[int, float]]] = defaultdict(list)
    missing = 0
    for member in relation["members"]:
        if member["type"] != "w":
            continue
        way = ways.get(member["ref"])
        if not way:
            missing += 1
            continue
        points = way["nodes"]
        for node_id, lat, lon in points:
            nodes[node_id] = (lat, lon)
        for first, second in zip(points, points[1:]):
            distance = haversine(first[1], first[2], second[1], second[2])
            if distance <= 0:
                continue
            adjacency[first[0]].append((second[0], distance))
            adjacency[second[0]].append((first[0], distance))
    return nodes, adjacency, missing


def nearest_rail_node(station: dict[str, Any], nodes: dict[int, tuple[float, float]], max_distance_m: float = 250.0) -> tuple[int | None, float]:
    best_id = None
    best_distance = float("inf")
    for node_id, (lat, lon) in nodes.items():
        distance = haversine(station["lat"], station["lon"], lat, lon)
        if distance < best_distance:
            best_id, best_distance = node_id, distance
    return (best_id, best_distance) if best_distance <= max_distance_m else (None, best_distance)


def rail_path(start: int, end: int, nodes: dict[int, tuple[float, float]], adjacency: dict[int, list[tuple[int, float]]]) -> tuple[list[int], float] | None:
    queue: list[tuple[float, int]] = [(0.0, start)]
    distances = {start: 0.0}
    previous: dict[int, int] = {}
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances.get(node):
            continue
        if node == end:
            path = [node]
            while path[-1] != start:
                path.append(previous[path[-1]])
            path.reverse()
            return path, distance
        for target, edge_distance in adjacency.get(node, []):
            candidate = distance + edge_distance
            if candidate < distances.get(target, float("inf")):
                distances[target] = candidate
                previous[target] = node
                heapq.heappush(queue, (candidate, target))
    return None


def station_sequence(relation: dict[str, Any], stations: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    sequence = []
    seen: set[int] = set()
    for member in relation["members"]:
        if member["type"] != "n" or member["ref"] in seen:
            continue
        station = stations.get(member["ref"])
        if not station:
            continue
        tags = station["tags"]
        is_stop = tags.get("railway") in {"station", "stop", "halt"} or tags.get("public_transport") == "stop_position"
        if not is_stop:
            continue
        seen.add(member["ref"])
        sequence.append({"osm_id": member["ref"], "name": tags.get("name", str(member["ref"])), "lat": station["lat"], "lon": station["lon"], "railway": tags.get("railway"), "public_transport": tags.get("public_transport")})
    return sequence


def build_rail(collector: RelationCollector, network: NetworkCollector) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = []
    validations = []
    for relation in collector.rail_relations:
        tags = relation["tags"]
        if tags.get("route") != "subway":
            continue
        stations = station_sequence(relation, network.station_nodes)
        rail_nodes, rail_adjacency, missing = relation_rail_graph(relation, network.rail_ways)
        station_nodes: list[int | None] = []
        station_join_distances: list[float] = []
        for station in stations:
            node_id, join_distance = nearest_rail_node(station, rail_nodes)
            station_nodes.append(node_id)
            station_join_distances.append(join_distance)
        geometry: list[list[float]] = []
        route_paths: list[list[int]] = []
        routing_failures = 0
        for start, end in zip(station_nodes, station_nodes[1:]):
            if start is None or end is None:
                routing_failures += 1
                continue
            result = rail_path(start, end, rail_nodes, rail_adjacency)
            if result is None:
                routing_failures += 1
                continue
            path, _distance = result
            route_paths.append(path)
            geometry.extend([[rail_nodes[node_id][0], rail_nodes[node_id][1]] for node_id in path if not geometry or rail_nodes[node_id] != tuple(geometry[-1])])
        geometry_length = sum(haversine(a[0], a[1], b[0], b[1]) for a, b in zip(geometry, geometry[1:]))
        continuity = "PASS" if geometry and missing == 0 and routing_failures == 0 else "FAIL"
        station_order = "PASS" if len(stations) >= 2 and all(haversine(a["lat"], a["lon"], b["lat"], b["lon"]) > 0 for a, b in zip(stations, stations[1:])) and all(distance <= 250 for distance in station_join_distances) else "FAIL"
        record = {
            "line_id": str(tags.get("ref", "")).strip(),
            "relation_id": relation["id"],
            "route": tags.get("route"),
            "direction_from": tags.get("from"),
            "direction_to": tags.get("to"),
            "name": tags.get("name"),
            "geometry": geometry,
            "geometry_length_m": round(geometry_length, 3),
            "station_sequence": stations,
            "station_join_distances_m": [round(distance, 3) for distance in station_join_distances],
            "validation": {
                "geometry_completeness": "PASS" if geometry and missing == 0 and routing_failures == 0 else "FAIL",
                "missing_way_count": missing,
                "geometry_discontinuity_count": routing_failures,
                "geometry_continuity": continuity,
                "station_count": len(stations),
                "joined_station_count": len(stations),
                "unmatched_station_count": sum(node_id is None for node_id in station_nodes),
                "station_ordering": station_order,
                "status": "PASS" if continuity == "PASS" and station_order == "PASS" else "FAIL",
            },
        }
        records.append(record)
        validations.append({
            "line_id": record["line_id"],
            "relation_id": record["relation_id"],
            "direction_from": record["direction_from"] or "",
            "direction_to": record["direction_to"] or "",
            "geometry_points": len(geometry),
            "geometry_length_m": round(geometry_length, 3),
            "missing_way_count": missing,
            "geometry_discontinuity_count": routing_failures,
            "station_count": len(stations),
            "joined_station_count": len(stations),
            "unmatched_station_count": sum(node_id is None for node_id in station_nodes),
            "station_ordering": station_order,
            "geometry_continuity": continuity,
            "status": record["validation"]["status"],
        })
    return records, validations


def connected_components(graph: dict[str, Any]) -> tuple[int, int]:
    neighbors: dict[int, set[int]] = defaultdict(set)
    for node, edges in graph["adj"].items():
        for target, _distance, _way, _speed in edges:
            neighbors[node].add(target)
            neighbors[target].add(node)
    remaining = set(graph["nodes"])
    count = 0
    largest = 0
    while remaining:
        start = remaining.pop()
        queue = deque([start])
        size = 1
        while queue:
            node = queue.popleft()
            for target in neighbors[node]:
                if target in remaining:
                    remaining.remove(target)
                    queue.append(target)
                    size += 1
        count += 1
        largest = max(largest, size)
    return count, largest


def write_graphs(network: NetworkCollector, restrictions: list[dict[str, Any]]) -> dict[str, Any]:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    summaries = {}
    for mode, graph in network.graphs.items():
        graph["adj"] = dict(graph["adj"])
        if mode == "car":
            graph["restrictions"] = [item for item in restrictions if item["from_way"] and item["to_way"] and item["via_node"]]
        component_count, largest_component = connected_components(graph)
        graph["stats"] = {
            "mode": mode,
            "way_count": graph.pop("way_count"),
            "node_count": len(graph["nodes"]),
            "directed_edge_count": graph.pop("edge_count"),
            "component_count": component_count,
            "largest_component_nodes": largest_component,
            "restriction_count": len(graph.get("restrictions", [])),
        }
        with gzip.open(GRAPH_DIR / f"{mode}.graph.pkl.gz", "wb", compresslevel=6) as handle:
            pickle.dump(graph, handle, protocol=pickle.HIGHEST_PROTOCOL)
        summaries[mode] = graph["stats"]
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Dataset v2 rail and local surface network references")
    parser.add_argument("--pbf", type=Path, default=PBF)
    args = parser.parse_args()
    if not args.pbf.exists():
        raise SystemExit(f"OSM PBF not found: {args.pbf}")
    relation_collector = RelationCollector()
    relation_collector.apply_file(str(args.pbf), locations=False, idx="flex_mem")
    network_collector = NetworkCollector(relation_collector.rail_way_ids, relation_collector.rail_node_ids)
    network_collector.apply_file(str(args.pbf), locations=True, idx="flex_mem")
    rail_records, validations = build_rail(relation_collector, network_collector)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    RAIL_PATH.write_text(json.dumps({"coordinate_system": "EPSG:4326", "source": "OpenStreetMap relation and way geometry", "lines": rail_records}, ensure_ascii=False, indent=2), encoding="utf-8")
    with RAIL_VALIDATION_PATH.open("w", newline="", encoding="utf-8") as handle:
        fields = list(validations[0]) if validations else ["line_id", "relation_id", "status"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(validations)
    graph_summaries = write_graphs(network_collector, relation_collector.restrictions)
    print(json.dumps({"rail_relations": len(rail_records), "rail_pass": sum(row["status"] == "PASS" for row in validations), "rail_fail": sum(row["status"] == "FAIL" for row in validations), "graph_summaries": graph_summaries}, ensure_ascii=False))


if __name__ == "__main__":
    main()
