# Seoul Synthetic Journey Generator

This is an independent generator for a synthetic labelled GPS evaluation dataset based on Seoul geography and public transport reference data.

This generator is being developed independently for a platform that is also under independent development.

Developer: Hayden Shin

Contact: min.developer@gmail.com

It does not read or tune against an external mobility classifier. It creates the journey first, keeps Ground Truth in separate files, applies sensor noise, validates the result, and freezes the dataset as a versioned artifact.

Dataset v3 is the current real-reference implementation. It uses a versioned
regional South Korea OSM PBF for bus and car road geometry, official Seoul bus
route and stop files, actual railway relation geometry, and separate local
car, walk, and bike graphs. The frozen external evaluation package is
`output/evaluation_dataset_v3` and contains 700 journeys.

This is not real user GPS, iPhone collection data, or a record of Seoul residents' movements. The correct description is a synthetic labelled GPS evaluation dataset generated from Seoul transport and geographic reference data.

## Project Purpose

The generator supports these labels: walk, bike, car, bus, and rail. Multimodal is a journey category, not a sixth GPS mode label. A multimodal journey contains real segment labels such as walk, rail, walk.

## Architecture

Reference data is kept under `reference_data`. Dataset v3 records source URLs,
licenses, dates, sizes, coordinate systems, and SHA-256 hashes in its reference
manifest. Bus route coverage is audited against all 718 official route records;
713 complete routes are eligible for generation and 5 remain excluded with
their failed stop pairs recorded.

Routing is separated from movement simulation. Routing chooses a reference corridor or transit sequence. Movement simulation adds variable speed, acceleration, deceleration, pauses, station dwell, stop and go behavior, and time profile variation.

GPS sensor simulation takes the true trajectory and creates a separate observed CSV. Ground Truth is written as a separate JSON file and is never copied into GPS columns.

Validation checks both file contracts and the relationship between GPS and Ground Truth. Visualization is a development output and is not part of the evaluation package.

## Reference Data

The current snapshot was prepared from OpenStreetMap through Overpass and OSRM. The raw downloads are intentionally ignored by Git. The preparation command can download them again.

Seoul public data source pages used for provenance are recorded in reference_data/manifests/reference_data_manifest.json.

Seoul bus route data: https://data.seoul.go.kr/dataList/OA-1095/S/1/datasetView.do

Seoul bus stop location data: https://data.seoul.go.kr/dataList/OA-15067/S/1/datasetView.do

Seoul Metro station data: https://data.seoul.go.kr/dataList/OA-22493/L/1/datasetView.do

OpenStreetMap data is available under ODbL. The compact processed snapshot contains 39 station records, 5 bus corridor records, and 12 OSRM surface corridors. The bus route records use public route identifiers and actual OSM stop positions for a reproducible corridor sample. They do not claim to be a complete timetable or the current complete geometry of those routes. Import the current Seoul bus route file before using this as a production route network.

## Data Preparation

Run this when the processed reference snapshot is missing or when a fresh snapshot is needed.

```text
python scripts/prepare_reference_data.py
python scripts/prepare_reference_data.py --refresh
```

The script keeps raw and processed data separate and writes the provenance manifest.

## Routing

Walk, bike, and car use separate local OSM graphs and profiles. Bus uses the
official ordered stop sequence plus locally routed OSM road geometry. Rail uses
validated OSM railway relation and way geometry with ordered station joins.
The v3 generator rejects missing geometry and does not use straight-line,
fabricated, or cross-mode fallback routes.

## Movement Simulation

All modes use variable speed profiles. Walk includes slow and fast walking, crossing pauses, short stops, and low speed near journey boundaries. Bike includes acceleration, deceleration, slow riding, and pedestrian area behavior. Car includes congestion, stop and go, signals, short stops, and faster road sections. Bus includes traffic variation and unequal stop dwell times. Rail includes departure acceleration, inter station movement, arrival braking, and station dwell.

## GPS Sensor Simulation

The default sampling interval is 5 seconds and can be changed in config/generator.yaml. The supported noise profiles are clean, normal, and noisy.

Clean represents good outdoor reception. Normal represents ordinary urban GPS behavior. Noisy represents a harder urban environment with larger coordinate jitter, more poor accuracy readings, and more missing points.

The noise model supports coordinate jitter, accuracy variation, interval jitter, speed noise, course noise, missing points, stationary drift, and temporary poor accuracy. Rail tunnel behavior is a synthetic approximation. It is not a claim about a specific mobile operating system sensor implementation.

## Ground Truth

Each trip has one JSON file with trip timestamps and ordered segments. Rail segments include the reference line and station sequence. Bus segments include the reference route and stop sequence. The GPS CSV contains only sensor like fields.

The GPS schema is schema_version, trip_id, device_id, sequence, timestamp, latitude, longitude, horizontal_accuracy_m, altitude_m, vertical_accuracy_m, speed_mps, and course_deg.

## Scenario Types

The generator varies short, medium, and long routes through different stored corridors, regions, time profiles, noise profiles, and transit patterns. Multimodal patterns include walk to rail to walk, walk to bus to walk, walk to bike to walk, walk to car to walk, bus and rail transfers, rail and bus transfers, and bike to rail journeys.

Hard cases include car versus bike, car versus bus, walk versus bike, transit proximity false positives, and transit sequence cases. These cases keep the original five labels and do not introduce a hidden sixth class.

## Dataset Generation

The small POC is generated first.

```text
python scripts/generate_dataset.py --poc
python scripts/validate_dataset.py output/poc
```

The v3 full version is generated with the configured target counts.

```text
python scripts/generate_dataset_v3.py --full --force
python scripts/validate_dataset_v3.py output/evaluation_dataset_v3_candidate
python scripts/write_v3_reports.py
python scripts/freeze_dataset_v3.py output/evaluation_dataset_v3_candidate
python scripts/export_dataset_v3.py output/evaluation_dataset_v3_candidate output/evaluation_dataset_v3
```

The generator uses seed 2026. The per journey random stream is derived from that seed and the journey number, so the same code, reference snapshot, configuration, and seed produce the same true trajectory and observations.

## Dataset Validation

The v3 validation suite checks journey endpoints, complete timelines, separate
Ground Truth, actual reference geometry, network fidelity at every GPS point,
physical speed and acceleration, transfers, GPS schema, and label leakage.
The final candidate passed 7,454 checks with zero failures and 370,650 point
level validations passed.

## Dataset Freeze

After validation, the dataset is frozen with:

```text
python scripts/freeze_dataset.py output/dataset_v1
```

The freeze manifest records dataset version, generator version, Git commit, seed, reference data hash, configuration hash, file hashes, validation counts, and freeze time. A later generator change must create a new dataset version instead of changing dataset_v1.

## Output Package

The generated dataset lives under `output/evaluation_dataset_v3_candidate`
before export. GPS files are under `gps`, Ground Truth files are under
`ground_truth`, reports are under `validation`, and the 700 development plots
are under `visualizations`.

The frozen evaluation package is exported with:

```text
python scripts/export_dataset_v3.py output/evaluation_dataset_v3_candidate output/evaluation_dataset_v3
```

The export contains GPS, Ground Truth, the 700 visualizations, manifests,
reference provenance, validation reports, release gate, and freeze hashes. It
does not contain generator source, raw downloads, or cache.

## Final Dataset Result

The v3 frozen dataset contains 700 journeys: walk 120, bike 110, car 110,
bus 100, rail 120, and multimodal 140. The candidate contains 370,650
observed GPS events, 700 Ground Truth files, 456 valid multimodal transfers,
and 700 visualizations.

The full hard case counts are recorded in output/dataset_v1/manifests/dataset_manifest.json. The generated examples include car near stations, walking near stations, parallel rail and road movement, car and bus confusion cases, slow bikes, fast walks, and transfer sequence cases.

## Limitations

The dataset is synthetic and cannot reproduce every behavior of real phones, users, traffic, or transport operations.

The rail tunnel observation model is an approximation. It includes sparse points, poor accuracy, missing points, and station area recovery, but it is not a measured mobile sensor trace.

Traffic variation is procedural. It is not a calibrated traffic simulation and should not be described as an exact reconstruction of Seoul traffic at a particular time.

The regional OSM extract is used because a Seoul-only extract did not cover
all official metropolitan bus stops. Five official routes remain excluded
because their required stop pairs have no connected regional graph path.
Station access uses validated station joins with an explicit fallback because
an entrance reference was not available in the acquired sources. These facts
are recorded in the v3 reference manifest and coverage audit.

## Development Timeline

The work was kept in small commits so the repository history records the build order.

The project scaffold was created first and the independent Git repository was initialized.

The configuration loader was made dependency free so the repository can read the small YAML configuration files without requiring PyYAML.

The reference feasibility audit approved a no API key acquisition plan.

The regional OSM extract and official Seoul bus files were acquired and hashed.

Separate car, walk, and bike reference graphs were validated, with railway
relation geometry retained for rail journeys.

All 718 official bus routes were audited and the 713 complete routes were
used for v3 generation. Five failed routes were recorded and excluded.

The v3 generator was changed to build complete journeys first, add actual
network based movement, insert routed walk transfer segments, and create
GPS observations from the true trajectory.

The final v3 candidate passed 7,454 independent checks, all 370,650 point
checks passed, all 456 transfer checks passed, and 700 journey plots were
created.

The Seoul reference preparation script, source manifest, station and bus stop snapshot, and processed network were added.

OSM derived surface corridors were then added to avoid direct coordinate lines for surface journeys.

The reference network, routing abstraction, and data models were added next.

Single mode generation, multimodal generation, movement profiles, and GPS sensor noise were added after routing.

The validation suite was added and the 13 journey POC passed all 224 checks.

Development trajectory visualizations were added for representative mode and hard case samples.

Dataset freeze and evaluation export were added after the POC was working.

The automated tests were added and passed 5 tests.

The full dataset was generated, passed 11,903 validation checks, frozen as dataset_v1, and exported as evaluation_dataset_v1.
