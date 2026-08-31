# Dataset v1 Geometry and Ground Truth Audit

Audit scope

This audit reads the frozen evaluation package, the generator source, the processed reference network, and the reference manifest. It does not modify, regenerate, or rewrite Dataset v1. Audit outputs are stored separately under this report folder.

## Direct Answers

Q1. Does a Ground Truth Line 5 journey start at a real Line 5 station and follow the real Line 5 station order?

PARTIALLY. The generator uses coordinates from records labelled line_5, but the compact sequence is not a complete Line 5 station list and its stored order places Gongdeok before Yeouido. The audit found 16 Line 5 rail segments that fail the known selected-station order check. The remaining Line 5 segments pass only the limited stored reference check.

Q2. Does the GPS follow actual Line 5 rail track geometry or an approximation?

STATION BASED APPROXIMATION. RAIL POLYLINE REFERENCE = NOT AVAILABLE. The code converts the selected station coordinates to a polyline and resamples each station to station segment with linear interpolation. Movement simulation and GPS noise are then applied.

Q3. Does a Bus Journey use the real bus route and stop order?

NO. It uses five public route identifiers and OSM stop positions selected near anchor points. The official Seoul bus route file and official route membership or sequence were not imported. The route is piecewise interpolation between selected stop coordinates.

Q4. Does a Car Journey follow real Seoul roads?

PARTIALLY YES. Car uses one of 12 precomputed OSRM driving geometries derived from OpenStreetMap. It does not perform arbitrary live origin destination routing at generation time. Walk and bike also reuse these driving corridor geometries.

Q5. Is this 700 Journey dataset sufficient for Canopy Bus and Rail Transit Context performance evaluation?

PARTIALLY. It is independent and useful for a controlled synthetic smoke test, but it is not sufficient for a claim about production transit context accuracy because full official bus route membership, full rail station sequences, and rail track geometry are absent. The generator contains no Canopy thresholds, scores, resolver rules, or production matching radius.

## Dataset Summary

Evaluation package: C:\Users\user\Desktop\seoul-synthetic-journey-generator\output\evaluation_dataset_v1

Ground Truth files: 700

GPS files: 700

Rail containing journeys: 237

Rail segments: 237

Rail segment counts by stored line: {'line_7': 34, 'line_2': 29, 'line_6': 24, 'line_3': 39, 'line_5': 27, 'line_1': 30, 'line_4': 27, 'line_9': 27}

Bus segments: 230

Car segments: 123

## Rail Generation Flow

For a rail journey, DatasetGenerator.generate_journey in src/seoul_generator/generator.py calls _route. Router.rail_route in src/seoul_generator/routing.py selects a stored line from ReferenceNetwork.stations_by_line, chooses a contiguous slice of that stored list, converts station coordinates to [latitude, longitude] pairs, and calls resample_polyline.

resample_polyline performs piecewise linear interpolation between station coordinates. It does not read a rail track geometry. The returned points go to generate_segment_points in src/seoul_generator/mobility.py. That function applies a procedural speed wave, rail speed bounds, and dwell positions. Dwell positions are evenly distributed over total route distance and are not read from the actual intermediate station coordinates.

The resulting true trajectory is passed to observe in src/seoul_generator/gps.py. That function adds coordinate jitter, accuracy variation, interval jitter, speed noise, course noise, missing points, stationary drift, and poor accuracy events. _write_ground_truth in src/seoul_generator/generator.py writes the segment mode and route metadata selected earlier. No geometry based reclassification occurs before Ground Truth is written.

## Line 5 Examples

The five examples below were read directly from evaluation_dataset_v1/ground_truth.

trip_000407 | rail | 마곡나루 -> 왕십리 | line_5 | 마곡나루 > 공덕 > 여의도 > 왕십리
trip_000415 | rail | 공덕 -> 왕십리 | line_5 | 공덕 > 여의도 > 왕십리
trip_000420 | rail | 김포공항 -> 여의도 | line_5 | 김포공항 > 마곡나루 > 공덕 > 여의도
trip_000445 | rail | 마곡나루 -> 여의도 | line_5 | 마곡나루 > 공덕 > 여의도
trip_000449 | rail | 공덕 -> 왕십리 | line_5 | 공덕 > 여의도 > 왕십리

The stored processed Line 5 reference is: 김포공항, 마곡나루, 공덕, 여의도, 왕십리. The known selected-station order is 김포공항, 마곡나루, 여의도, 공덕, 왕십리. This is why the compact reference check can pass while the actual selected-station order check can fail.

## Station Sequence Audit

Total rail containing journeys: 237

Total rail segments audited: 237

Passed against the generator's stored contiguous reference slice: 237

Failed against the stored contiguous reference slice: 0

Line 5 selected-order failures against the known actual selected order: 16

For lines other than Line 5, a complete actual station order could not be verified because the repository has no full official line sequence reference. The CSV records this as NOT_VERIFIABLE_FULL_REFERENCE rather than claiming a pass.

Checks performed: missing station names, missing line keys, sequence order, duplicates, compact reference membership, and Line 5 selected order. Full intermediate station omission cannot be checked from the available reference because the processed network itself is a compact sample.

## Station Distance Results

The rail CSV reports median, p95, and maximum distance from observed GPS to the nearest expected station in the selected station sequence. These are station based approximation distances. They are not distances to rail geometry.

Start and end distances are measured against the first and last expected station for each rail segment. Multimodal rail segments include the connector added by _join_route in src/seoul_generator/generator.py, so the first rail segment point can be away from the boarding station.

## Bus Audit

The bus CSV contains 230 bus segments. Every generated route ID is present in the processed compact reference and every selected stop name is present in that compact route. That is only an internal consistency result.

Official route membership and official stop sequence are NOT_VERIFIABLE from the repository. prepare_reference_data.py selects the nearest OSM stop for each anchor and records a public route ID. routing.py then resamples the selected stop coordinates. No official bus route geometry is used.

## Car, Walk, and Bike Audit

The car CSV contains 123 segments. A car segment stores a corridor_id and source field from the 12 OSRM geometries in reference_data/processed/seoul_network.json. This is real OSM derived road geometry for those corridors, but it is a limited precomputed corridor set.

Walk and bike call the same Router.surface_route method and therefore also use driving profile OSRM corridors. There is no separate pedestrian network or bicycle network in the processed reference data. Procedural movement speed does not make the geometry walkable or bike legal.

## Movement and Time Audit

Speeds are generated by hand-authored rules and bounded random variation in src/seoul_generator/mobility.py. BASE_SPEEDS, SPEED_RANGES, sine waves, hard case multipliers, random pauses, and stop dwell ranges are used. No measured traffic distribution, rail timetable, bus timetable, or real acceleration distribution is used.

Rail has a procedural speed wave and evenly distributed dwell positions. Bus has procedural stop dwell and speed variation. Timestamps are produced at the configured interval, while GPS observations add bounded interval jitter.

This audit treats implied speeds above 8 m/s for walk, 20 m/s for bike, 50 m/s for car, 35 m/s for bus, or 80 m/s for rail as mode speed failures. Absolute implied acceleration above 8 m/s2 is also reported as a failure. These are audit thresholds, not measured Seoul traffic limits.

walk: median 2.052 m/s, p95 6.902 m/s, max 51.500 m/s, max acceleration 67.100 m/s2, teleport events 0, status FAIL
bike: median 3.272 m/s, p95 7.567 m/s, max 44.198 m/s, max acceleration 30.374 m/s2, teleport events 0, status FAIL
car: median 4.463 m/s, p95 10.040 m/s, max 31.903 m/s, max acceleration 16.774 m/s2, teleport events 0, status FAIL
bus: median 4.631 m/s, p95 9.983 m/s, max 46.015 m/s, max acceleration 35.814 m/s2, teleport events 0, status FAIL
rail: median 9.523 m/s, p95 16.056 m/s, max 49.053 m/s, max acceleration 26.492 m/s2, teleport events 0, status FAIL
unknown: median  m/s, p95  m/s, max  m/s, max acceleration  m/s2, teleport events 0, status PASS

Physical consistency failure rows: 5. The repository's original validation also passed its 11,903 checks. This audit adds implied speed, acceleration, duplicate time, zero time movement, and teleport calculations by mode.

## Ground Truth Reliability

Scenario Intent and Actual Generated Geometry are separate concepts in the source code only up to trajectory creation. The mode is selected before route generation. _write_ground_truth then copies the selected segment mode and route metadata into JSON. There is no second pass that proves the generated coordinates are on a real rail track, official bus route, or mode-accessible network.

Ground Truth is therefore reliable as the generator's scenario label and metadata record. It is not evidence that the generated geometry satisfies a complete real-world network constraint.

## Production Independence

Canopy Transit Context score: NO

Rail threshold: NO

Bus threshold: NO

Resolver rules: NO

Production matching radius: NO

Production classification logic: NO

The repository search and source inspection found no Canopy production reference. This supports independence and means there is no direct evaluation leakage from those fields.

## Evaluation Judgement

Movement ML Evaluation: PASS_WITH_LIMITATIONS. The package has 700 journeys, five single-mode labels, multimodal segments, procedural variation, noise profiles, reproducible seeds, and separate Ground Truth. Geometry is not a complete citywide network simulation.

Transit Context Evaluation: FAIL for production claims and PASS_WITH_LIMITATIONS for a synthetic smoke test. Bus route membership and full rail sequences are not authoritative, and rail track geometry is absent.

Rail Detection Evaluation: PASS_WITH_LIMITATIONS. Rail sequences are selected from stored station lists and GPS endpoints are station based, but the line lists are compact and Line 5 contains an order error. There is no rail polyline.

Bus Detection Evaluation: FAIL for real route fidelity and PASS_WITH_LIMITATIONS for a synthetic stop proximity test. The public route IDs and OSM stop coordinates do not prove official route membership or stop order.

Car Detection Evaluation: PASS_WITH_LIMITATIONS. Car geometry is OSM derived for 12 precomputed OSRM corridors, but this is not a general Seoul road network sample.

Multimodal Segmentation Evaluation: PASS_WITH_LIMITATIONS. Segment labels and boundaries are generated and separated from GPS, but _join_route adds synthetic connectors and no geometry based segment verification is performed.

## Visual Audit

The plots folder contains six short, medium, and long rail examples plus four multimodal rail segment examples. Each plot shows observed GPS, expected station points, station sequence numbering, and the station to station reference. No rail polyline is shown because RAIL POLYLINE REFERENCE = NOT AVAILABLE.

## Hash and File Safety

Frozen evaluation package hashes before and after audit: UNCHANGED

The audit writes only under reports/dataset_v1_geometry_audit. Dataset v1 files were not changed.

## Files Produced

DATASET_V1_GEOMETRY_AUDIT.md

rail_journey_audit.csv

bus_journey_audit.csv

car_journey_audit.csv

physical_consistency.csv

reference_data_audit.md

plots/
