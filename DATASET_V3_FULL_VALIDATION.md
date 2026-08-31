# Dataset v3 Full Validation

Dataset version: evaluation_dataset_v3

This is a synthetic GPS evaluation dataset generated without real users. It
is not a collected iPhone trace and must not be described as one.

## Release Gate

| Check | Result |
|---|---|
| Journey count | 700 |
| GPS files | 700 |
| Ground Truth files | 700 |
| GPS point validations | 370650 PASS, 0 FAIL |
| Independent validation checks | 7454 PASS, 0 FAIL |
| Multimodal transfer checks | 456 PASS, 0 FAIL |
| Journey visualizations | 700 |
| Dataset release gate | PASS |

## Source Coverage

The bus audit contains all 718 official Seoul route records. Regional OSM
road geometry produced 713 complete routes and 40949 routable stop pairs out
of 40958 official stop pairs. Five routes with nine failed stop pairs remain
excluded because the regional graph could not provide connected paths. Their
failure reasons are recorded in `reference_data/v3/bus_coverage_audit.csv`.

Walk, bike, and car use separate local graph artifacts. Bus uses the official
stop order and OSM road paths. Rail uses validated OSM railway relation and
way geometry with ordered station joins. A station entrance source was not
available, so the explicit station join fallback is recorded in rail Ground
Truth metadata.

## Required Report

The detailed Q1 to Q13 release answers are in
`output/evaluation_dataset_v3_candidate/validation/JOURNEY_REALITY_VALIDATION.md`.
All answers are YES. The report records the synthetic nature of the data and
the remaining bus source exclusions.
