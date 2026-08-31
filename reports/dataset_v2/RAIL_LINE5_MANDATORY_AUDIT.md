# Line 5 Mandatory Audit

The audit uses the validated OpenStreetMap subway relations and railway ways in `reference_data/v2/rail_network.json`.

Line 5 validated relations: 8
Main direction A: 상일동 -> 방화
Main direction B: 방화 -> 상일동
Direction sequence reverse consistency: PASS
Five OD tests: PASS

The line geometry is composed from OSM railway way paths. No station-to-station straight interpolation is used.

Artifacts:
- `rail_line5_mandatory_audit.csv`
- `line5_mandatory_geometry.png`
