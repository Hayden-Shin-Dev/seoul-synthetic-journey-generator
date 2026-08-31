from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import osmium
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "reference_data" / "v2" / "raw"
MANIFEST = ROOT / "reference_data" / "v2" / "reference_data_manifest.json"


class OsmAuditHandler(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.node_count = 0
        self.way_count = 0
        self.rail_way_count = 0
        self.railway_tags: Counter[str] = Counter()
        self.highway_tags: Counter[str] = Counter()
        self.route_relations: list[dict[str, Any]] = []

    def node(self, node: osmium.osm.Node) -> None:
        self.node_count += 1

    def way(self, way: osmium.osm.Way) -> None:
        self.way_count += 1
        tags = dict(way.tags)
        highway = tags.get("highway")
        if highway:
            self.highway_tags[highway] += 1
        railway = tags.get("railway")
        if railway:
            self.rail_way_count += 1
            self.railway_tags[railway] += 1

    def relation(self, relation: osmium.osm.Relation) -> None:
        tags = dict(relation.tags)
        if tags.get("type") == "route" or tags.get("route") in {"subway", "train", "light_rail", "railway"}:
            self.route_relations.append(
                {
                    "id": relation.id,
                    "tags": tags,
                    "member_count": len(relation.members),
                }
            )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(
    *,
    source_name: str,
    provider: str,
    source_url: str,
    path: Path,
    snapshot_or_publication_date: str,
    license_name: str,
    crs: str,
    row_count: int | None,
    geometry_type: str,
    coordinate_coverage: dict[str, Any],
    known_limitations: list[str],
    schema: list[str] | None = None,
    encoding: str | None = None,
) -> dict[str, Any]:
    return {
        "source_name": source_name,
        "provider": provider,
        "source_url": source_url,
        "downloaded_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
        "snapshot_or_publication_date": snapshot_or_publication_date,
        "local_filename": str(path.relative_to(ROOT)).replace("\\", "/"),
        "byte_size": path.stat().st_size,
        "sha256": sha256(path),
        "license": license_name,
        "crs": crs,
        "row_count": row_count,
        "geometry_type": geometry_type,
        "coordinate_coverage": coordinate_coverage,
        "known_limitations": known_limitations,
        **({"schema": schema} if schema is not None else {}),
        **({"encoding": encoding} if encoding is not None else {}),
    }


def _coordinate_coverage(df: pd.DataFrame, x_col: str, y_col: str) -> dict[str, Any]:
    x = pd.to_numeric(df[x_col], errors="coerce")
    y = pd.to_numeric(df[y_col], errors="coerce")
    valid = x.notna() & y.notna() & x.between(120, 132) & y.between(30, 40)
    return {
        "valid_rows": int(valid.sum()),
        "invalid_rows": int((~valid).sum()),
        "longitude_min": float(x[valid].min()),
        "longitude_max": float(x[valid].max()),
        "latitude_min": float(y[valid].min()),
        "latitude_max": float(y[valid].max()),
        "observed_column_order": "X longitude, Y latitude",
    }


def audit_bus_files(records: list[dict[str, Any]]) -> dict[str, Any]:
    route_path = RAW / "seoul_bus_route_stops_20260804.xlsx"
    stop_path = RAW / "seoul_bus_stops_20260804.xlsx"
    route_df = pd.read_excel(route_path, dtype={"ARS_ID": str})
    stop_df = pd.read_excel(stop_path, dtype={"ARS_ID": str})
    expected_route = ["ROUTE_ID", "노선명", "순번", "NODE_ID", "ARS_ID", "정류소명", "X좌표", "Y좌표"]
    expected_stop = ["NODE_ID", "ARS_ID", "정류소명", "X좌표", "Y좌표", "정류소타입"]
    if route_df.columns.tolist() != expected_route:
        raise ValueError(f"unexpected route schema: {route_df.columns.tolist()}")
    if stop_df.columns.tolist() != expected_stop:
        raise ValueError(f"unexpected stop schema: {stop_df.columns.tolist()}")
    route_duplicates = int(route_df.duplicated(["ROUTE_ID", "순번"]).sum())
    stop_duplicates = int(stop_df.duplicated(["NODE_ID"]).sum())
    route_valid = _coordinate_coverage(route_df, "X좌표", "Y좌표")
    stop_valid = _coordinate_coverage(stop_df, "X좌표", "Y좌표")
    records.extend(
        [
            file_record(
                source_name="Seoul bus route stop sequence snapshot",
                provider="Seoul Metropolitan Government, Seoul data portal",
                source_url="https://data.seoul.go.kr/dataList/OA-1095/S/1/datasetView.do",
                path=route_path,
                snapshot_or_publication_date="2026-08-04",
                license_name="Public Nuri Type 1 as marked on source portal",
                crs="Portal declares WGS84 (EPSG-5179); observed X/Y values are longitude/latitude degrees and are validated as EPSG:4326",
                row_count=len(route_df),
                geometry_type="ordered stop points",
                coordinate_coverage=route_valid,
                known_limitations=[
                    "The downloaded schema has no dedicated direction column.",
                    "ROUTE_ID and sequence are preserved as supplied; direction is not invented.",
                    f"Duplicate ROUTE_ID plus sequence rows: {route_duplicates}.",
                ],
                schema=route_df.columns.tolist(),
                encoding="XLSX workbook, Unicode cell values",
            ),
            file_record(
                source_name="Seoul bus stop location snapshot",
                provider="Seoul Metropolitan Government, Seoul data portal",
                source_url="https://data.seoul.go.kr/dataList/OA-15067/S/1/datasetView.do",
                path=stop_path,
                snapshot_or_publication_date="2026-08-04",
                license_name="Public Nuri Type 1 as marked on source portal",
                crs="Portal declares WGS84 (EPSG-5179); observed X/Y values are longitude/latitude degrees and are validated as EPSG:4326",
                row_count=len(stop_df),
                geometry_type="Point",
                coordinate_coverage=stop_valid,
                known_limitations=[
                    "ARS_ID values must remain strings so leading zeroes are preserved.",
                    f"Duplicate NODE_ID rows: {stop_duplicates}.",
                ],
                schema=stop_df.columns.tolist(),
                encoding="XLSX workbook, Unicode cell values",
            ),
        ]
    )
    return {
        "route_rows": len(route_df),
        "route_columns": route_df.columns.tolist(),
        "route_unique_route_ids": int(route_df["ROUTE_ID"].nunique()),
        "route_unique_public_names": int(route_df["노선명"].nunique()),
        "route_duplicate_route_sequence": route_duplicates,
        "route_missing_values": {str(k): int(v) for k, v in route_df.isna().sum().items()},
        "stop_rows": len(stop_df),
        "stop_columns": stop_df.columns.tolist(),
        "stop_duplicate_node_ids": stop_duplicates,
        "stop_missing_values": {str(k): int(v) for k, v in stop_df.isna().sum().items()},
    }


def audit_osm(records: list[dict[str, Any]]) -> dict[str, Any]:
    path = RAW / "Seoul.osm.pbf"
    handler = OsmAuditHandler()
    handler.apply_file(str(path), locations=False, idx="flex_mem")
    records.append(
        file_record(
            source_name="Seoul OpenStreetMap extract",
            provider="BBBike extract service and OpenStreetMap contributors",
            source_url="https://download.bbbike.org/osm/bbbike/Seoul/Seoul.osm.pbf",
            path=path,
            snapshot_or_publication_date="BBBike extract downloaded 2026-08-31; source snapshot date is recorded by provider metadata where available",
            license_name="Open Database License 1.0 for OSM data",
            crs="WGS84 / EPSG:4326",
            row_count=None,
            geometry_type="nodes, ways, and relations",
            coordinate_coverage={
                "node_count": handler.node_count,
                "way_count": handler.way_count,
                "rail_way_count": handler.rail_way_count,
                "railway_tags": dict(handler.railway_tags),
                "highway_tags_top_30": dict(handler.highway_tags.most_common(30)),
                "route_relation_count": len(handler.route_relations),
            },
            known_limitations=[
                "This is an OSM extract and completeness is subject to OSM tagging and the extract boundary.",
                "Rail relation and station joins require separate validation before use.",
                "OSM geometry does not provide official bus route membership; Seoul bus files remain authoritative for that.",
            ],
        )
    )
    return {
        "node_count": handler.node_count,
        "way_count": handler.way_count,
        "rail_way_count": handler.rail_way_count,
        "railway_tags": dict(handler.railway_tags),
        "highway_tags_top_30": dict(handler.highway_tags.most_common(30)),
        "route_relations": handler.route_relations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Dataset v2 source files and write their manifest")
    parser.parse_args()
    records: list[dict[str, Any]] = []
    bus_summary = audit_bus_files(records)
    osm_summary = audit_osm(records)
    manifest = {
        "dataset_version": "evaluation_dataset_v2",
        "manifest_version": "1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "coordinate_system": "EPSG:4326 for normalized v2 geometry",
        "routing_engine": {
            "name": "Local mode-specific graph router",
            "implementation": "pyosmium OSM parsing plus NetworkX-compatible adjacency graphs",
            "reason": "Docker and Java are unavailable in the current environment; this keeps routing local, reproducible, and profile-separated without a hosted API.",
        },
        "sources": records,
        "bus_schema_audit": bus_summary,
        "osm_audit": osm_summary,
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(MANIFEST), "source_count": len(records), "bus": bus_summary, "osm": {k: v for k, v in osm_summary.items() if k != "route_relations"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
