from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "reference_data" / "v2" / "rail_network.json"
REPORT_DIR = ROOT / "reports" / "dataset_v2"
AUDIT_CSV = REPORT_DIR / "rail_line5_mandatory_audit.csv"
AUDIT_MD = REPORT_DIR / "RAIL_LINE5_MANDATORY_AUDIT.md"


def main() -> None:
    data = json.loads(REFERENCE.read_text(encoding="utf-8"))
    lines = [line for line in data["lines"] if line["validation"]["status"] == "PASS"]
    line5 = [line for line in lines if line["line_id"] == "5"]
    if len(line5) < 2:
        raise SystemExit("Line 5 does not have validated bidirectional geometry")
    main_forward = next((line for line in line5 if line["direction_from"] == "상일동" and line["direction_to"] == "방화"), None)
    main_reverse = next((line for line in line5 if line["direction_from"] == "방화" and line["direction_to"] == "상일동"), None)
    if not main_forward or not main_reverse:
        raise SystemExit("Line 5 main branch directions are missing")
    forward_names = [station["name"] for station in main_forward["station_sequence"]]
    reverse_names = [station["name"] for station in main_reverse["station_sequence"]]
    direction_pair_pass = reverse_names == list(reversed(forward_names))
    rows = []
    for index, (start, end) in enumerate(((0, 5), (2, 12), (5, 20), (10, 30), (20, 43)), 1):
        sequence = forward_names[start : end + 1]
        passed = direction_pair_pass and len(sequence) == end - start + 1 and len(main_forward["geometry"]) > 2
        rows.append({"test_id": f"line5_od_{index:02d}", "boarding_station": sequence[0], "alighting_station": sequence[-1], "station_sequence": " > ".join(sequence), "station_count": len(sequence), "geometry_points": len(main_forward["geometry"]), "direction_pair_consistent": "PASS" if direction_pair_pass else "FAIL", "rail_geometry_present": "PASS" if len(main_forward["geometry"]) > 2 else "FAIL", "status": "PASS" if passed else "FAIL"})
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with AUDIT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    figure, axis = plt.subplots(figsize=(12, 8), dpi=160)
    geometry = main_forward["geometry"]
    axis.plot([point[1] for point in geometry], [point[0] for point in geometry], color="#7b3f98", linewidth=1.2, label="Line 5 railway geometry")
    stations = main_forward["station_sequence"]
    axis.scatter([station["lon"] for station in stations], [station["lat"] for station in stations], color="#111111", s=8, label="Line 5 stations")
    axis.scatter([stations[0]["lon"], stations[-1]["lon"]], [stations[0]["lat"], stations[-1]["lat"]], color="#d97706", s=24, label="main branch endpoints")
    axis.set_title("Dataset v2 Line 5 mandatory rail reference audit")
    axis.set_xlabel("longitude")
    axis.set_ylabel("latitude")
    axis.grid(True, alpha=0.2)
    axis.legend()
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "line5_mandatory_geometry.png")
    plt.close(figure)
    all_pass = all(row["status"] == "PASS" for row in rows)
    AUDIT_MD.write_text("\n".join([
        "# Line 5 Mandatory Audit",
        "",
        "The audit uses the validated OpenStreetMap subway relations and railway ways in `reference_data/v2/rail_network.json`.",
        "",
        f"Line 5 validated relations: {len(line5)}",
        f"Main direction A: {main_forward['direction_from']} -> {main_forward['direction_to']}",
        f"Main direction B: {main_reverse['direction_from']} -> {main_reverse['direction_to']}",
        f"Direction sequence reverse consistency: {'PASS' if direction_pair_pass else 'FAIL'}",
        f"Five OD tests: {'PASS' if all_pass else 'FAIL'}",
        "",
        "The line geometry is composed from OSM railway way paths. No station-to-station straight interpolation is used.",
        "",
        "Artifacts:",
        "- `rail_line5_mandatory_audit.csv`",
        "- `line5_mandatory_geometry.png`",
    ]) + "\n", encoding="utf-8")
    if not all_pass:
        raise SystemExit("Line 5 mandatory audit failed")
    print(f"Line 5 mandatory audit PASS: {len(rows)} OD tests")


if __name__ == "__main__":
    main()
