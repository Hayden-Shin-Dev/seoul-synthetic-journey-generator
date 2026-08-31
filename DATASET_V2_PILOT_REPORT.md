# Dataset v2 Pilot Report

Audit date: 2026-08-31

The pilot was generated after the prototype gate with independent seed 32026.
It contains 50 journeys: 9 walk, 8 bike, 8 car, 8 bus, 9 rail, and 8
multimodal journeys.

The independent validator passed 339 of 339 checks with zero failures. The
audit covered file counts, mode-specific metadata, actual reference geometry,
GPS contracts, timestamp order, physical limits, transfer distances, and
category counts. `scripts/audit_dataset_v2.py` also passed its independent
manifest and artifact checks.

The pilot was completed before the full dataset stage. It is a gate report,
not a frozen evaluation package.

Final pilot rerun with the accepted sampling fix also passed 339 of 339
validation checks and the independent audit with zero failures.
