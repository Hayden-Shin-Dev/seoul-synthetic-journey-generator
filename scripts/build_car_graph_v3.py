from __future__ import annotations

import argparse
import gzip
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import osmium

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_network_v2 import allowed_way, haversine, is_oneway, speed_mps  # noqa: E402


class CarCollector(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.nodes: dict[int, tuple[float, float]] = {}
        self.adj: dict[int, list[tuple[int, float, int, float]]] = defaultdict(list)
        self.way_count = 0
        self.edge_count = 0

    def way(self, way: osmium.osm.Way) -> None:
        tags = dict(way.tags)
        points = [(node.ref, node.lat, node.lon) for node in way.nodes if node.location.valid()]
        if len(points) < 2 or not allowed_way(tags, "car"):
            return
        self.way_count += 1
        for node_id, lat, lon in points:
            self.nodes[node_id] = (lat, lon)
        direction = is_oneway(tags, "car")
        velocity = speed_mps(tags, "car")
        for first, second in zip(points, points[1:]):
            distance = haversine(first[1], first[2], second[1], second[2])
            if distance <= 0:
                continue
            if direction >= 0:
                self.adj[first[0]].append((second[0], distance, way.id, velocity))
                self.edge_count += 1
            if direction <= 0:
                self.adj[second[0]].append((first[0], distance, way.id, velocity))
                self.edge_count += 1


class RestrictionCollector(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.restrictions: list[dict] = []

    def relation(self, relation: osmium.osm.Relation) -> None:
        tags = dict(relation.tags)
        restriction = str(tags.get("restriction", ""))
        if tags.get("type") != "restriction" or not restriction.startswith("no_"):
            return
        item = {"from_way": 0, "to_way": 0, "via_node": 0, "restriction": restriction}
        for member in relation.members:
            if member.type == "w" and member.role == "from":
                item["from_way"] = member.ref
            elif member.type == "w" and member.role == "to":
                item["to_way"] = member.ref
            elif member.type == "n" and member.role == "via":
                item["via_node"] = member.ref
        if item["from_way"] and item["to_way"] and item["via_node"]:
            self.restrictions.append(item)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build only the regional car graph for Dataset v3")
    parser.add_argument("--pbf", type=Path, default=ROOT / "reference_data" / "v3" / "raw" / "south-korea-latest.osm.pbf")
    args = parser.parse_args()
    collector = CarCollector()
    collector.apply_file(str(args.pbf), locations=True, idx="flex_mem")
    restrictions = RestrictionCollector()
    restrictions.apply_file(str(args.pbf), locations=False, idx="flex_mem")
    graph = {"nodes": collector.nodes, "adj": dict(collector.adj), "restrictions": restrictions.restrictions, "stats": {"mode": "car", "way_count": collector.way_count, "node_count": len(collector.nodes), "directed_edge_count": collector.edge_count, "restriction_count": len(restrictions.restrictions), "source": str(args.pbf)}}
    out = ROOT / "reference_data" / "v3" / "graphs"
    out.mkdir(parents=True, exist_ok=True)
    with gzip.open(out / "car.graph.pkl.gz", "wb", compresslevel=6) as handle:
        pickle.dump(graph, handle, protocol=pickle.HIGHEST_PROTOCOL)
    (out / "car_graph_stats.json").write_text(json.dumps(graph["stats"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(graph["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
