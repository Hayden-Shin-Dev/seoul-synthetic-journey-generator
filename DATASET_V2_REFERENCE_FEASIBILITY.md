# Dataset v2 Reference Feasibility Audit

Audit date: 2026-08-31

This audit is a gate before any Dataset v2 generator work. The existing v1
generator and v1 outputs were not modified during this audit.

The v1 reference snapshot is not sufficient for an external evaluation dataset
because it contains station points and sampled corridors rather than complete,
mode-specific transport networks. Dataset v2 must be built only after the
missing reference data has been acquired, checked, and recorded with hashes.

## Decision Summary

The recommended baseline does not require an API key. It uses downloadable
Seoul public data for bus route membership and stop sequence, OpenStreetMap
extracts for railway and road geometry, and locally built routing graphs for
car, walk, and bike. No current mode is `READY` because the required source
files and local graphs are not present in this repository.

No mode is currently `NEEDS_API_KEY` or `BLOCKED`. This is a feasibility
decision, not a claim that the v2 data has already been downloaded or that the
v2 implementation is complete.

## Feasibility Table

| Mode | Needed real data | Currently owned | Additional acquisition | Candidate source | API key required | Implementation possible |
|---|---|---|---|---|---|---|
| Rail | Actual railway way geometry, line membership, ordered station joins, and station coordinates | OSM-derived station points and compact line-order samples only. No railway way geometry or verified complete line relations | Download an OSM PBF extract, extract subway and rail ways and route relations, join stations, and validate every selected line and direction | [Geofabrik South Korea extracts](https://download.geofabrik.de/asia/south-korea.html) or [BBBike Seoul extracts](https://download.bbbike.org/osm/bbbike/Seoul/). Seoul Metro metadata can supplement station identity through the [Seoul public data page](https://data.seoul.go.kr/dataList/OA-22493/L/1/datasetView.do) | No | Yes, after download and relation, coverage, and station-join validation. Status: `NEEDS_DOWNLOAD` |
| Bus | Official route membership, direction, stop sequence, stop coordinates, and a road-network path between consecutive stops | Five public route identifiers and sparse OSM stop samples only. No official route file or verified route stop sequence | Download the current Seoul bus route and stop files, preserve route and direction fields, then route each consecutive stop pair on the local road graph | [Seoul bus route and stop sequence data](https://data.seoul.go.kr/dataList/OA-1095/S/1/datasetView.do) plus [Seoul bus stop locations](https://data.seoul.go.kr/dataList/OA-15067/S/1/datasetView.do) and an OSM road extract | No for the direct file downloads. A keyed legacy API is not part of the baseline | Yes, after download, schema inspection, route sequence validation, and local road routing. Status: `NEEDS_DOWNLOAD` |
| Car | Drivable road network, one-way rules, turn restrictions, access tags, and route geometry | Twelve OSRM driving corridor geometries derived from OSM. No complete local road graph | Download a Seoul or South Korea OSM PBF and build a local car routing graph | [Geofabrik South Korea extracts](https://download.geofabrik.de/asia/south-korea.html) or [BBBike Seoul extracts](https://download.bbbike.org/osm/bbbike/Seoul/) with local OSRM or GraphHopper | No | Yes, after local graph build and route smoke tests. Status: `NEEDS_DOWNLOAD` |
| Walk | Pedestrian-accessible network, foot access restrictions, crossings, footways, pedestrian areas, and route geometry | No pedestrian network. Existing surface corridors are driving routes and are not valid walk references | Download an OSM PBF and build a separate foot profile. Validate access tags, crossings, disconnected areas, and station-area paths | OSM extract from [Geofabrik](https://download.geofabrik.de/asia/south-korea.html) or [BBBike](https://download.bbbike.org/osm/bbbike/Seoul/) with local [GraphHopper profiles](https://github.com/graphhopper/graphhopper/blob/master/docs/core/profiles.md) or a separately extracted OSRM foot profile | No | Yes, after a separate foot graph and access validation. Status: `NEEDS_DOWNLOAD` |
| Bike | Bicycle-accessible network, cycleways, bicycle access restrictions, and route geometry | No bicycle network. Existing driving corridors must not be reused | Download an OSM PBF and build a separate bicycle profile. Validate cycleway preference, bicycle access, barriers, and forbidden motorways | OSM extract from [Geofabrik](https://download.geofabrik.de/asia/south-korea.html) or [BBBike](https://download.bbbike.org/osm/bbbike/Seoul/) with local [GraphHopper profiles](https://github.com/graphhopper/graphhopper/blob/master/docs/core/profiles.md) or a separately extracted OSRM bicycle profile | No | Yes, after a separate bike graph and access validation. Status: `NEEDS_DOWNLOAD` |

## Current Repository Assessment

The current processed reference file is
`reference_data/processed/seoul_network.json`.

It currently contains:

- Eight compact rail line lists with 50 station records in the processed file.
- Five bus records with four selected OSM stop positions per route.
- Twelve OSRM driving corridor geometries.
- No full railway way network.
- No official Seoul bus route or stop-sequence file.
- No local car, foot, or bicycle routing graph.

The existing manifest already records the important bus limitation: the bus
records are a corridor sample using public route identifiers and OSM stop
positions. They are not a complete current Seoul bus route reference.

The existing routing code linearly resamples station and stop points for rail
and bus, and uses stored driving corridors for surface modes. That is not an
acceptable v2 reference method. In particular, a car corridor cannot be used
as a walk or bike network, and station or stop points cannot be connected by
straight interpolation when a real network route is required.

## Source Findings

### Official Seoul public data

The Seoul public data portal exposes downloadable files for bus route and
route-stop information, and a separate bus stop location dataset. These files
are the preferred source for bus route membership and ordered stop data. The
portal marks the public data as Public Nuri Type 1 on the source pages. The
exact downloaded filename, publication date, file size, column names, and hash
must be recorded after download rather than assumed in code.

The Seoul Metro source is useful for station identity and line metadata, but
the current repository does not have a full track geometry file from it. It
must not be treated as a substitute for railway geometry until the downloaded
content is inspected and verified.

### OpenStreetMap extracts

OSM is the preferred no-key source for the actual Seoul railway and road
network geometry. A regional PBF is more suitable for reproducible processing
than depending on a live Overpass query during dataset generation. Geofabrik
and BBBike provide downloadable extracts. OSM-derived data requires ODbL
attribution and provenance in the v2 reference manifest.

Rail processing must use ordered OSM railway way geometry and validated line
relations or another explicitly verified line-order source. It must fail when
a station cannot be joined to the selected line or when line coverage is
incomplete. It must not invent a station sequence.

### Local routing engines

OSRM documents separate preprocessing for car, bicycle, and foot profiles. A
profile is applied while extracting the graph, not as an unrecorded query-time
switch, so each v2 mode must record its profile and graph build inputs.

GraphHopper supports local OSM PBF import and separate car, bike, and foot
profiles with access and road-priority customization. It is the recommended
single local engine for the three surface modes if one engine is preferred.
OSRM remains a valid alternative when separately extracted mode profiles are
maintained.

## Mode Implementation Rules For v2

### Rail

The route source must contain actual railway geometry. For every generated rail
segment, the Ground Truth must record the source extract, line or relation
identifier, ordered station identifiers, and the geometry method. A rail path
must be assembled from railway ways or a validated rail route relation, not
from a straight line between station coordinates.

### Bus

The official Seoul file is authoritative for route membership and stop order.
The road network is authoritative for the drivable path between consecutive
stops. Each stop pair must be locally routed with the bus or car-compatible
road profile, and a missing path must fail the build. The implementation must
preserve route direction where the source distinguishes directions.

### Car

Car segments must be generated from the local car graph. The graph must honor
one-way, access, turn, and road-class rules represented by the selected OSM
profile. Stored v1 corridors may not be used as the v2 network substitute.

### Walk

Walk segments must be generated from a foot graph. The profile must use
pedestrian-accessible ways and crossings and must exclude ways that are not
walkable under the selected access rules. The walk graph and its profile must
be separate from the car graph even when both originate from the same PBF.

### Bike

Bike segments must be generated from a bicycle graph. The profile must use
bicycle access and cycleway tags and apply bicycle-specific exclusions and
preferences. The bike graph and its profile must be separate from both the
car and foot graphs.

## API Key Assessment

The proposed baseline requires no API key:

1. Seoul bus files are available as direct public downloads from the Seoul
   data portal.
2. Geofabrik and BBBike provide downloadable OSM extracts.
3. OSRM and GraphHopper can be run locally after the OSM download.
4. No hosted routing API is needed for generation.

The v1 Overpass snapshot is not a sufficient v2 acquisition plan. Live
Overpass requests can fail or time out for large geometry queries, so v2 should
use a versioned PBF download and local processing. If a required official file
later turns out to require authentication or a key, the build must stop and
report the API name, provider, data fields, reason, cost, issuance process,
and no-key alternative before using it.

## Acquisition And Validation Gate

Generator v2 must not start until these conditions are met:

1. Every downloaded source has a URL, provider, license, publication or
   snapshot date, local filename, byte size, SHA-256 hash, and coordinate
   system recorded in a reference manifest.
2. Rail line coverage and ordered station joins pass a reportable validation
   check for every line used by the dataset.
3. Bus route IDs, directions, stop membership, and stop sequence are verified
   against the downloaded official file. Every routed stop pair has a local
   road path.
4. Car, foot, and bike graphs are built separately and each has successful
   route smoke tests on representative Seoul origins and destinations.
5. The generator rejects missing geometry, disconnected required paths,
   missing mode profiles, and unverified transit sequences.
6. Ground Truth records the source and geometry method for every segment.
7. No v2 route is produced by straight interpolation, arbitrary coordinates,
   fabricated routes, fabricated station order, or cross-mode graph reuse.

Until this gate passes, no v2 dataset can be called complete or frozen.

## Audit Conclusion

The reference problem is feasible without an API key, but the current
repository is not ready for Dataset v2. The next approved stage is acquisition
and validation of the official bus files and versioned OSM extract, followed by
local mode-specific graph construction. Only after those artifacts pass the
gate above should Generator v2 implementation begin.
