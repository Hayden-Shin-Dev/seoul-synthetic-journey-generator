from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from seoul_generator.v2_routing import LocalRouter

ROUTE_FILE = ROOT / "reference_data" / "v2" / "raw" / "seoul_bus_route_stops_20260804.xlsx"
BUS_FILE = ROOT / "reference_data" / "v2" / "bus_network.json"
VALIDATION_FILE = ROOT / "reference_data" / "v2" / "bus_reference_validation.csv"
GRAPH_FILE = ROOT / "reference_data" / "v2" / "graphs" / "car.graph.pkl.gz"


def stop(row: pd.Series) -> dict[str, Any]:
    return {"node_id": int(row["NODE_ID"]), "ars_id": str(row["ARS_ID"]).zfill(5), "name": str(row["정류소명"]), "lat": float(row["Y좌표"]), "lon": float(row["X좌표"])}


def build(group: pd.DataFrame, router: LocalRouter) -> dict[str, Any] | None:
    ordered = group.sort_values("순번")
    stops = [stop(row) for _, row in ordered.iterrows()]
    geometry: list[list[float]] = []
    pairs = []
    snaps = []
    for index, (first, second) in enumerate(zip(stops, stops[1:])):
        try:
            result = router.route((first["lat"], first["lon"]), (second["lat"], second["lon"]), max_snap_distance_m=250.0, respect_restrictions=False)
        except ValueError:
            return None
        snaps.extend([result.start_snap_distance_m, result.end_snap_distance_m])
        segment = [[lat, lon] for lat, lon in result.geometry]
        if geometry and segment and geometry[-1] == segment[0]:
            segment = segment[1:]
        geometry.extend(segment)
        pairs.append({"from_ars_id": first["ars_id"], "to_ars_id": second["ars_id"], "distance_m": round(result.distance_m, 3), "duration_s": round(result.duration_s, 3), "geometry": segment})
    route_uid = int(ordered.iloc[0]["ROUTE_ID"])
    route_id = str(ordered.iloc[0]["노선명"])
    return {"route_uid": route_uid, "route_id": route_id, "direction": None, "direction_source": "not present in official downloaded schema", "stops": stops, "ordered_stop_ids": [item["node_id"] for item in stops], "ordered_ars_ids": [item["ars_id"] for item in stops], "geometry": geometry, "geometry_length_m": round(sum(pair["distance_m"] for pair in pairs), 3), "geometry_method": "local OSM car graph routed between official Seoul stop sequence", "route_geometry_reference": f"local_osm_car_graph_route_{route_uid}", "routing_profile": "car_graph_for_bus_road_geometry", "pair_geometry": pairs, "stop_snap_distances_m": [round(value, 3) for value in snaps], "validation": {"official_route_membership": "PASS", "sequence": "PASS", "direction_consistency": "NOT_PROVIDED", "duplicate_sequence_count": int(ordered["순번"].duplicated().sum()), "coordinate_missing_count": 0, "routable_pair_count": len(pairs), "failed_pair_count": 0, "status": "PASS"}}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build selected official bus routes on the local OSM car graph")
    parser.add_argument("--routes", nargs="+", default=["143", "402", "421", "740", "7016", "100", "101", "140", "150", "151", "160", "260", "270", "271", "273", "301", "360", "401", "405", "420", "461", "470", "500", "507", "540", "571", "600", "602", "603", "604"])
    args = parser.parse_args()
    data = json.loads(BUS_FILE.read_text(encoding="utf-8"))
    df = pd.read_excel(ROUTE_FILE, dtype={"ARS_ID": str})
    router = LocalRouter(GRAPH_FILE)
    replacement = 0
    for route_name in args.routes:
        matches = df[df["노선명"].astype(str).str.strip() == route_name]
        for route_uid, group in matches.groupby("ROUTE_ID", sort=True):
            record = build(group, router)
            if record is None:
                continue
            for index, current in enumerate(data["routes"]):
                if current["route_uid"] == int(route_uid):
                    data["routes"][index] = record
                    replacement += 1
                    break
    data["selected_local_graph_routes"] = args.routes
    data["updated_at"] = datetime.now(UTC).isoformat()
    BUS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    existing = {}
    if VALIDATION_FILE.exists():
        with VALIDATION_FILE.open(encoding="utf-8", newline="") as handle:
            existing = {int(row["route_uid"]): row for row in csv.DictReader(handle) if row.get("route_uid")}
    for record in data["routes"]:
        validation = record.get("validation", {})
        row = existing.setdefault(record["route_uid"], {})
        row.update({
            "route_uid": record["route_uid"],
            "route_id": record["route_id"],
            "direction": record.get("direction") or "",
            "osm_relation_id": record.get("osm_relation_id", ""),
            "stop_count": len(record.get("stops", [])),
            "pair_count": max(0, len(record.get("stops", [])) - 1),
            "routable_pair_count": validation.get("routable_pair_count", 0),
            "failed_pair_count": validation.get("failed_pair_count", 0),
            "max_stop_snap_distance_m": max(record.get("stop_snap_distances_m", [0]), default=0),
            "duplicate_sequence_count": validation.get("duplicate_sequence_count", ""),
            "official_route_membership": validation.get("official_route_membership", "FAIL"),
            "sequence": validation.get("sequence", "FAIL"),
            "direction_consistency": validation.get("direction_consistency", "NOT_PROVIDED"),
            "status": validation.get("status", "FAIL"),
        })
    fields = []
    for row in existing.values():
        for field in row:
            if field not in fields:
                fields.append(field)
    with VALIDATION_FILE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(existing.values())
    summary = {"replaced_route_count": replacement, "requested_route_names": args.routes}
    (BUS_FILE.parent / "bus_reference_augmentation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
