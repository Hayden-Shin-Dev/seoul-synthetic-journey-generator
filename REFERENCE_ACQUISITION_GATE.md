# Reference Acquisition Gate

Gate date: 2026-08-31

This gate covers the reference catalog that Dataset v2 is allowed to use. It
does not alter Dataset v1. A route or relation that fails validation is not
used as a fallback source.

| Mode | Status |
|---|---|
| Rail | PASS |
| Bus | PASS |
| Car | PASS |
| Walk | PASS |
| Bike | PASS |

## Evidence

### Rail

PASS means a real OSM railway way path and a validated ordered station
sequence are available for the catalog used by v2. The extract contains 161
subway route relations, of which 73 pass geometry continuity and station join
validation. All eight Line 5 relations pass, including both directions for the
main branches. The Line 5 mandatory OD audit is recorded in
`reference_data/v2/rail_reference_validation.csv` and the generated Line 5
test report.

Relations with missing ways, disconnected route members, or insufficient
station joins are excluded. No station sequence is invented and no station
pair is connected by straight interpolation.

### Bus

PASS means the catalog contains official Seoul route and stop sequence rows,
with road geometry routed on OSM-derived graph data. The official source has
718 route IDs. Fifty-five route IDs pass complete stop-pair routing and are
available to v2. The remaining 663 route IDs are recorded as FAIL and are
excluded from generation because the available OSM relation or road graph did
not provide a complete validated path. OSM stop IDs are not used as a
substitute for official route membership.

The downloaded source schema and missing-value audit are recorded in
`reference_data/v2/reference_data_manifest.json`.

### Car

PASS means the local car graph is operational. It contains OSM road ways with
one-way and access handling, disconnected components are measured, and 5,555
car restriction relations are loaded for turn-aware routing. Twenty real
Seoul origin-destination smoke routes passed.

### Walk

PASS means a separate foot graph is operational. It includes pedestrian ways
and accessible road classes and excludes motorways and trunk roads unless an
explicit foot access tag allows them. Twenty smoke routes passed on the foot
graph.

### Bike

PASS means a separate bicycle graph is operational. It includes bicycle ways
and bicycle-compatible roads, excludes motorways and ordinary footways, and
applies bicycle access and one-way tags. Twenty smoke routes passed on the
bicycle graph.

## Source And Build Artifacts

- `reference_data/v2/reference_data_manifest.json`
- `reference_data/v2/rail_network.json`
- `reference_data/v2/rail_reference_validation.csv`
- `reference_data/v2/bus_network.json`
- `reference_data/v2/bus_reference_validation.csv`
- `reference_data/v2/graphs/car.graph.pkl.gz`
- `reference_data/v2/graphs/walk.graph.pkl.gz`
- `reference_data/v2/graphs/bike.graph.pkl.gz`
- `reports/dataset_v2/routing_smoke_tests/`

The chosen local router is implemented in `src/seoul_generator/v2_routing.py`.
It reads the versioned graph artifacts without a hosted routing service or an
API key. The PBF and official XLSX files remain under the ignored immutable
raw reference directory and are identified by SHA-256 in the manifest.

The v2 generator may proceed only with records whose gate status is PASS. A
missing route, missing profile, failed path, or failed validation remains a
hard failure; it is never replaced with arbitrary coordinates or a straight
line.
