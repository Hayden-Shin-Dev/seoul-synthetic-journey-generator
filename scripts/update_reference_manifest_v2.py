from __future__ import annotations

import gzip
import hashlib
import json
import pickle
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "reference_data" / "v2"
MANIFEST = REFERENCE / "reference_data_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, object]:
    return {"local_filename": str(path.relative_to(ROOT)).replace("\\", "/"), "byte_size": path.stat().st_size, "sha256": sha256(path)}


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rail = json.loads((REFERENCE / "rail_network.json").read_text(encoding="utf-8"))
    bus = json.loads((REFERENCE / "bus_network.json").read_text(encoding="utf-8"))
    validation = json.loads((REFERENCE / "bus_reference_augmentation_summary.json").read_text(encoding="utf-8"))
    artifacts = {}
    for name in ("rail_network.json", "rail_reference_validation.csv", "bus_network.json", "bus_reference_validation.csv", "bus_reference_summary.json", "bus_reference_augmentation_summary.json"):
        artifacts[name] = file_record(REFERENCE / name)
    graphs = {}
    for mode in ("car", "walk", "bike"):
        path = REFERENCE / "graphs" / f"{mode}.graph.pkl.gz"
        with gzip.open(path, "rb") as handle:
            graph = pickle.load(handle)
        graphs[mode] = {**file_record(path), "stats": graph["stats"]}
    manifest["reference_network_artifacts"] = {
        "rail_relation_count": len(rail["lines"]),
        "rail_valid_relation_count": sum(line["validation"]["status"] == "PASS" for line in rail["lines"]),
        "rail_line_5_valid_relation_count": sum(line["line_id"] == "5" and line["validation"]["status"] == "PASS" for line in rail["lines"]),
        "official_bus_route_count": len(bus["routes"]),
        "usable_bus_route_count": sum(route["validation"]["status"] == "PASS" for route in bus["routes"]),
        "excluded_bus_route_count": sum(route["validation"]["status"] == "FAIL" for route in bus["routes"]),
        "bus_augmentation": validation,
        "artifacts": artifacts,
        "local_graphs": graphs,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest["reference_network_artifacts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
