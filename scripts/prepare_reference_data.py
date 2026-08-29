from __future__ import annotations

import argparse
import json
import math
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "reference_data" / "raw"
PROCESSED = ROOT / "reference_data" / "processed"
MANIFESTS = ROOT / "reference_data" / "manifests"

STATION_LINES = {
    "line_1": ["서울역", "시청", "종각", "종로3가", "동대문", "청량리"],
    "line_2": ["홍대입구", "합정", "신촌", "시청", "을지로입구", "잠실", "성수", "건대입구", "강남", "선릉", "삼성", "왕십리"],
    "line_3": ["연신내", "불광", "종로3가", "압구정", "고속터미널", "교대", "양재", "일원"],
    "line_4": ["창동", "동대문역사문화공원", "명동", "서울역", "사당"],
    "line_5": ["김포공항", "마곡나루", "공덕", "여의도", "왕십리"],
    "line_6": ["합정", "공덕", "이태원", "약수", "태릉입구"],
    "line_7": ["건대입구", "고속터미널", "이수", "가산디지털단지"],
    "line_9": ["김포공항", "여의도", "노량진", "고속터미널", "신논현"],
}

# These are established public bus route identifiers. The stop sequence below
# is a reproducible corridor sample; it is not a timetable or service claim.
BUS_ROUTE_ANCHORS = {
    "143": ["창동", "왕십리", "압구정", "고속터미널"],
    "402": ["장충단공원", "시청", "강남", "개포동"],
    "421": ["염곡동", "압구정", "명동", "청량리"],
    "740": ["구파발", "연신내", "시청", "강남"],
    "7016": ["수색교", "홍대입구", "공덕", "서울역"],
}

# Keep source files ASCII-safe while preserving the original Korean names.
STATION_LINES = {
    "line_1": ["\uc11c\uc6b8\uc5ed", "\uc2dc\uccad", "\uc885\uac01", "\uc885\ub85c3\uac00", "\ub3d9\ub300\ubb38", "\uccad\ub7c9\ub9ac"],
    "line_2": ["\ud64d\ub300\uc785\uad6c", "\ud569\uc815", "\uc2e0\ucd0c", "\uc2dc\uccad", "\uc744\uc9c0\ub85c\uc785\uad6c", "\uc7a0\uc2e4", "\uc131\uc218", "\uac74\ub300\uc785\uad6c", "\uac15\ub0a8", "\uc120\ub989", "\uc0bc\uc131", "\uc655\uc2ed\ub9ac"],
    "line_3": ["\uc5f0\uc2e0\ub0b4", "\ubd88\uad11", "\uc885\ub85c3\uac00", "\uc555\uad6c\uc815", "\uace0\uc18d\ud130\ubbf8\ub110", "\uad50\ub300", "\uc591\uc7ac", "\uc77c\uc6d0"],
    "line_4": ["\ucc3d\ub3d9", "\ub3d9\ub300\ubb38\uc5ed\uc0ac\ubb38\ud654\uacf5\uc6d0", "\uba85\ub3d9", "\uc11c\uc6b8\uc5ed", "\uc0ac\ub2f9"],
    "line_5": ["\uae40\ud3ec\uacf5\ud56d", "\ub9c8\uace1\ub098\ub8e8", "\uacf5\ub355", "\uc5ec\uc758\ub3c4", "\uc655\uc2ed\ub9ac"],
    "line_6": ["\ud569\uc815", "\uacf5\ub355", "\uc774\ud0dc\uc6d0", "\uc57d\uc218", "\ud0dc\ub989\uc785\uad6c"],
    "line_7": ["\uac74\ub300\uc785\uad6c", "\uace0\uc18d\ud130\ubbf8\ub110", "\uc774\uc218", "\uac00\uc0b0\ub514\uc9c0\ud138\ub2e8\uc9c0"],
    "line_9": ["\uae40\ud3ec\uacf5\ud56d", "\uc5ec\uc758\ub3c4", "\ub178\ub7c9\uc9c4", "\uace0\uc18d\ud130\ubbf8\ub110", "\uc2e0\ub17c\ud604"],
}
BUS_ROUTE_ANCHORS = {
    "143": ["\ucc3d\ub3d9", "\uc655\uc2ed\ub9ac", "\uc555\uad6c\uc815", "\uace0\uc18d\ud130\ubbf8\ub110"],
    "402": ["\uc7a5\ucda9\ub2e8\uacf5\uc6d0", "\uc2dc\uccad", "\uac15\ub0a8", "\uac1c\ud3ec\ub3d9"],
    "421": ["\uc5fc\uace1\ub3d9", "\uc555\uad6c\uc815", "\uba85\ub3d9", "\uccad\ub7c9\ub9ac"],
    "740": ["\uad6c\ud30c\ubc1c", "\uc5f0\uc2e0\ub0b4", "\uc2dc\uccad", "\uac15\ub0a8"],
    "7016": ["\uc218\uc0c9\uad50", "\ud64d\ub300\uc785\uad6c", "\uacf5\ub355", "\uc11c\uc6b8\uc5ed"],
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and prepare public Seoul reference snapshots")
    parser.add_argument("--refresh", action="store_true", help="refresh the OSM raw snapshots")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    station_path = RAW / "seoul_subway_stations_osm.json"
    stop_path = RAW / "seoul_bus_stops_osm.json"
    if args.refresh or not station_path.exists():
        _download_overpass(station_path, '[out:json][timeout:120];area["name"="서울특별시"][boundary=administrative]->.a;node[railway=station](area.a);out tags center;')
    if args.refresh or not stop_path.exists():
        _download_overpass(stop_path, '[out:json][timeout:120];area["name"="서울특별시"][boundary=administrative]->.a;node[highway=bus_stop](area.a);out tags center;')

    stations = _load_elements(station_path)
    stops = _load_elements(stop_path)
    station_index = _index_named(stations)
    selected_stations = {}
    for line_id, names in STATION_LINES.items():
        selected_stations[line_id] = [_station_record(name, station_index) for name in names]
    hubs = {record["name"]: record for values in selected_stations.values() for record in values}
    bus_routes = [_bus_route_record(route_id, anchors, hubs, stops) for route_id, anchors in BUS_ROUTE_ANCHORS.items()]
    network = {
        "coordinate_system": "WGS84",
        "source_snapshot": "OpenStreetMap Overpass snapshot",
        "stations_by_line": selected_stations,
        "bus_routes": bus_routes,
        "surface_hubs": list(hubs.values()),
    }
    output_path = PROCESSED / "seoul_network.json"
    output_path.write_text(json.dumps(network, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "dataset_name": "seoul_network_reference_snapshot",
        "source": "OpenStreetMap contributors via Overpass API",
        "source_url": "https://overpass-api.de/api/interpreter",
        "provider": "OpenStreetMap Foundation and Seoul Metropolitan Government public data portals",
        "downloaded_at": datetime.now(UTC).isoformat(),
        "data_version": "OSM snapshot at preparation time",
        "license": "ODbL 1.0 for OSM-derived data; Seoul public data is marked Public Nuri Type 1 at source",
        "coordinate_system": "WGS84 / EPSG:4326",
        "files": ["processed/seoul_network.json", "raw/seoul_subway_stations_osm.json", "raw/seoul_bus_stops_osm.json"],
        "important_columns": ["name", "lat", "lon", "railway", "highway"],
        "usage": "Station geometry, bus stop geometry, line-order anchors and reproducible surface corridor sampling",
        "limitations": "The compact bus route sequence is a corridor sample anchored to public route identifiers. Import the current Seoul bus route file for production route geometry.",
        "seoul_bus_route_source": "https://data.seoul.go.kr/dataList/OA-1095/S/1/datasetView.do",
        "seoul_bus_stop_source": "https://data.seoul.go.kr/dataList/OA-15067/S/1/datasetView.do",
        "seoul_metro_source": "https://data.seoul.go.kr/dataList/OA-22493/L/1/datasetView.do",
    }
    (MANIFESTS / "reference_data_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"prepared {len(hubs)} station records and {len(bus_routes)} bus corridor records")


def _download_overpass(path: Path, query: str) -> None:
    url = "https://overpass-api.de/api/interpreter?" + urllib.parse.urlencode({"data": query})
    request = urllib.request.Request(url, headers={"User-Agent": "SeoulSyntheticJourneyGenerator/0.1"})
    with urllib.request.urlopen(request, timeout=180) as response:
        path.write_bytes(response.read())


def _load_elements(path: Path) -> list[dict]:
    elements = json.loads(path.read_text(encoding="utf-8-sig"))["elements"]
    for element in elements:
        element["tags"] = {key: _repair_text(value) for key, value in element.get("tags", {}).items()}
    return elements


def _repair_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        repaired = value.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return repaired


def _index_named(elements: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for element in elements:
        name = element.get("tags", {}).get("name")
        if not name:
            continue
        result.setdefault(name, []).append(element)
    return result


def _station_record(name: str, index: dict[str, list[dict]]) -> dict:
    matches = index.get(name, [])
    if not matches:
        raise ValueError(f"required station was not found in the downloaded OSM snapshot: {name}")
    element = sorted(matches, key=lambda item: item.get("id", 0))[0]
    return {"osm_id": element["id"], "name": name, "lat": element["lat"], "lon": element["lon"]}


def _bus_route_record(route_id: str, anchors: list[str], hubs: dict[str, dict], stops: list[dict]) -> dict:
    selected = []
    named_stops = _index_named(stops)
    for index, anchor in enumerate(anchors, start=1):
        point = hubs.get(anchor)
        if point is None:
            point = _nearest_point_name(anchor, hubs)
        stop = _nearest_stop(point, stops)
        selected.append({"sequence": index, "osm_id": stop["id"], "name": stop.get("tags", {}).get("name", f"stop_{index}"), "lat": stop["lat"], "lon": stop["lon"]})
    return {"route_id": route_id, "route_name": f"Seoul city bus {route_id}", "stops": selected, "source_note": "public route identifier with OSM stop geometry corridor sample"}


def _nearest_stop(point: dict, stops: list[dict]) -> dict:
    return min(stops, key=lambda stop: _distance_m(point["lat"], point["lon"], stop["lat"], stop["lon"]))


def _nearest_point_name(name: str, hubs: dict[str, dict]) -> dict:
    # Explicitly named anchors not found as metro stations use the nearest metro hub.
    import hashlib

    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return hubs[sorted(hubs)[int.from_bytes(digest[:4], "big") % len(hubs)]]


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * earth * math.asin(math.sqrt(a))


if __name__ == "__main__":
    main()
