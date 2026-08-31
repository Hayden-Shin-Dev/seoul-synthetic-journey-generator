# Dataset v2 Prototype Report

Audit date: 2026-08-31

The Dataset v2 prototype was generated with seed 22026 from the acquired
reference package recorded in `reference_data/v2/reference_data_manifest.json`.
The generator wrote 60 journeys: 10 walk, 10 bike, 10 car, 10 bus, 10 rail,
and 10 multimodal. Six journeys contain a rail segment on Line 5, exceeding
the required five journey check.

The prototype uses actual PBF-derived rail and surface network geometry and
official Seoul bus stop sequence data. Every true trajectory point is sampled
along the selected reference polyline. GPS observations are stored separately
from true trajectories and Ground Truth.

Independent validation passed 402 of 402 checks with zero failures. The checks
covered file contracts, timestamp order, GPS coordinates and sequences,
physical speed and teleport limits, mode-specific Ground Truth metadata,
reference geometry error, multimodal transfer distance, and category counts.

All 60 journey visualizations were generated under
`output/dataset_v2_prototype/visualizations` and show the true route, observed
GPS points, and available bus stop or rail station anchors.

This report is a prototype gate only. It is not the full frozen evaluation
package and does not replace the pilot or full-dataset audits.
