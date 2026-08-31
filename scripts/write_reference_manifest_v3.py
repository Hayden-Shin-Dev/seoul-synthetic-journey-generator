from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source(path: Path, url: str, provider: str, license_name: str, note: str = "") -> dict:
    return {"local_filename": str(path.relative_to(ROOT)).replace("\\", "/"), "url": url, "provider": provider, "license": license_name, "byte_size": path.stat().st_size, "sha256": sha256(path), "coordinate_system": "EPSG:4326", "note": note}


def main() -> None:
    v2 = ROOT / "reference_data" / "v2"
    v3 = ROOT / "reference_data" / "v3"
    manifest = {"dataset_version": "reference_v3", "created_at": datetime.now(UTC).isoformat(), "api_key_required": False, "osm_attribution": "OpenStreetMap contributors, ODbL 1.0", "sources": {"regional_osm_pbf": source(v3 / "raw" / "south-korea-latest.osm.pbf", "https://download.geofabrik.de/asia/south-korea-latest.osm.pbf", "Geofabrik", "ODbL 1.0", "Regional extract selected because Seoul-only coverage missed official metropolitan bus stops"), "official_bus_route_stops": source(v2 / "raw" / "seoul_bus_route_stops_20260804.xlsx", "https://data.seoul.go.kr/dataList/OA-1095/S/1/datasetView.do", "Seoul Open Data", "Public Nuri Type 1"), "official_bus_stops": source(v2 / "raw" / "seoul_bus_stops_20260804.xlsx", "https://data.seoul.go.kr/dataList/OA-15067/S/1/datasetView.do", "Seoul Open Data", "Public Nuri Type 1")}, "derived_artifacts": {}, "coverage": json.loads((v3 / "bus_coverage_summary.json").read_text(encoding="utf-8")), "limitations": ["Ten official routes contain 14 stop pairs that remain unroutable on the regional OSM car graph and are excluded from v3 generation.", "The official downloaded schema does not expose route direction as a separate field."]}
    for path in [v3 / "bus_network.json", v3 / "bus_coverage_audit.csv", v3 / "bus_coverage_summary.json", v3 / "graphs" / "car.graph.pkl.gz", v3 / "graphs" / "car_graph_stats.json", v2 / "rail_network.json", v2 / "graphs" / "walk.graph.pkl.gz", v2 / "graphs" / "bike.graph.pkl.gz"]:
        if path.exists():
            manifest["derived_artifacts"][str(path.relative_to(ROOT)).replace("\\", "/")] = {"byte_size": path.stat().st_size, "sha256": sha256(path)}
    (v3 / "reference_data_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"sources": len(manifest["sources"]), "derived_artifacts": len(manifest["derived_artifacts"]), "coverage": manifest["coverage"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
