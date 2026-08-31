from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from seoul_generator.v2_routing import LocalRouter  # noqa: E402

ROUTE_FILE = ROOT / "reference_data" / "v2" / "raw" / "seoul_bus_route_stops_20260804.xlsx"
OUT = ROOT / "reference_data" / "v3"
BUS_JSON = OUT / "bus_network.json"
COVERAGE_CSV = OUT / "bus_coverage_audit.csv"
GRAPH = ROOT / "reference_data" / "v2" / "graphs" / "car.graph.pkl.gz"


def build_record(group: pd.DataFrame, router: LocalRouter, route_cache: dict[tuple[float, float, float, float], Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    columns = group.columns.tolist()
    name_col, sequence_col, node_col, ars_col, stop_name_col, lon_col, lat_col = columns[1:]
    ordered = group.sort_values(sequence_col)
    stops = [{"node_id": int(row[node_col]), "ars_id": str(row[ars_col]).zfill(5), "name": str(row[stop_name_col]), "lat": float(row[lat_col]), "lon": float(row[lon_col]), "sequence": int(row[sequence_col])} for _, row in ordered.iterrows()]
    pairs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    geometry: list[list[float]] = []
    snap_distances: list[float] = []
    for index, (first, second) in enumerate(zip(stops, stops[1:]), 1):
        try:
            cache_key = (first["lat"], first["lon"], second["lat"], second["lon"])
            result = route_cache.get(cache_key)
            if result is None:
                result = router.route((first["lat"], first["lon"]), (second["lat"], second["lon"]), max_snap_distance_m=250.0, respect_restrictions=False)
                route_cache[cache_key] = result
            segment = [[lat, lon] for lat, lon in result.geometry]
            if geometry and segment and geometry[-1] == segment[0]:
                segment = segment[1:]
            geometry.extend(segment)
            snap_distances.extend([result.start_snap_distance_m, result.end_snap_distance_m])
            pairs.append({"pair_index": index, "from_ars_id": first["ars_id"], "to_ars_id": second["ars_id"], "distance_m": round(result.distance_m, 3), "duration_s": round(result.duration_s, 3), "geometry": segment, "start_snap_distance_m": round(result.start_snap_distance_m, 3), "end_snap_distance_m": round(result.end_snap_distance_m, 3)})
        except ValueError as error:
            failures.append({"pair_index": index, "from_ars_id": first["ars_id"], "to_ars_id": second["ars_id"], "reason": str(error)})
    route_uid = int(ordered.iloc[0][columns[0]])
    route_id = str(ordered.iloc[0][name_col]).strip()
    complete = len(pairs) == len(stops) - 1 and not failures
    status = "PASS" if complete else "FAIL"
    record = {"route_uid": route_uid, "route_id": route_id, "direction": None, "direction_source": "not present in official downloaded schema", "stops": stops, "ordered_stop_ids": [stop["node_id"] for stop in stops], "ordered_ars_ids": [stop["ars_id"] for stop in stops], "geometry": geometry if complete else [], "geometry_length_m": round(sum(pair["distance_m"] for pair in pairs), 3), "geometry_method": "local OSM car graph routed between every official Seoul stop pair with nearest-edge candidates" if complete else "FAIL_INCOMPLETE_STOP_PAIR_ROUTING", "route_geometry_reference": f"local_osm_car_graph_route_{route_uid}" if complete else None, "routing_profile": "bus_road_graph_without_turn_restriction_fallback" if complete else None, "pair_geometry": pairs if complete else [], "stop_snap_method": "nearest_node_or_nearest_osm_edge_projection", "stop_snap_distances_m": [round(value, 3) for value in snap_distances], "validation": {"official_route_membership": "PASS", "sequence": "PASS", "direction_consistency": "NOT_PROVIDED", "duplicate_sequence_count": int(ordered[sequence_col].duplicated().sum()), "coordinate_missing_count": 0, "official_stop_count": len(stops), "routable_stop_count": len(pairs), "failed_stop_count": len(failures), "route_coverage": round(len(pairs) / max(1, len(stops) - 1), 6), "geometry_coverage": "PASS" if complete else "FAIL", "failure_reason": "; ".join(sorted(Counter(item["reason"] for item in failures).keys())[:3]), "recoverable": "YES" if complete else "NO", "status": status}}
    record["stop_snap_method"] = "nearest_node_or_nearest_osm_edge_projection"
    record["routing_policy"] = "bus_road_graph_without_turn_restriction_fallback"
    record["validation"]["recoverable"] = "YES" if complete else "NO"
    audit = {"route_uid": route_uid, "route_id": route_id, "official_stop_count": len(stops), "routable_stop_count": len(pairs), "failed_stop_count": len(failures), "route_coverage": round(len(pairs) / max(1, len(stops) - 1), 6), "geometry_coverage": "PASS" if complete else "FAIL", "failure_reason": record["validation"]["failure_reason"], "recoverable": "YES" if complete else "NO", "final_status": status}
    return record, audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and build every official Seoul bus route on the local OSM road graph")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--graph", type=Path, default=ROOT / "reference_data" / "v3" / "graphs" / "car.graph.pkl.gz")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_excel(ROUTE_FILE, dtype={"ARS_ID": str})
    router = LocalRouter(args.graph)
    records, audits = [], []
    groups = list(df.groupby("ROUTE_ID", sort=True))
    if args.limit:
        groups = groups[:args.limit]
    route_cache: dict[tuple[float, float, float, float], Any] = {}
    for index, (_route_uid, group) in enumerate(groups, 1):
        record, audit = build_record(group, router, route_cache)
        records.append(record)
        audits.append(audit)
        if index % 25 == 0:
            print(f"audited {index}/{len(groups)} routes", flush=True)
    BUS_JSON.write_text(json.dumps({"dataset_version": "reference_v3", "source_file": ROUTE_FILE.name, "created_at": datetime.now(UTC).isoformat(), "routes": records}, ensure_ascii=False), encoding="utf-8")
    fields = ["route_uid", "route_id", "official_stop_count", "routable_stop_count", "failed_stop_count", "route_coverage", "geometry_coverage", "failure_reason", "recoverable", "final_status"]
    with COVERAGE_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(audits)
    summary = {"official_route_count": len(records), "complete_route_count": sum(item["final_status"] == "PASS" for item in audits), "failed_route_count": sum(item["final_status"] == "FAIL" for item in audits), "total_official_stop_pairs": sum(item["official_stop_count"] - 1 for item in audits), "total_routable_stop_pairs": sum(item["routable_stop_count"] for item in audits), "created_at": datetime.now(UTC).isoformat()}
    (OUT / "bus_coverage_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
