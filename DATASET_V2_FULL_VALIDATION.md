# Dataset v2 Full Validation

## Final Answers

| Question | Answer |
|---|---|
| Q1. Is the dataset generated from versioned real Seoul reference data? | YES |
| Q2. Does every included rail route use actual railway geometry? | YES |
| Q3. Does every included bus route use official stop sequence and real road geometry? | YES |
| Q4. Do car, walk, and bike use separate local network graphs? | YES |
| Q5. Are straight interpolation and fabricated coordinates rejected? | YES |
| Q6. Are true trajectories generated before GPS observations? | YES |
| Q7. Are GPS observations separate from Ground Truth? | YES |
| Q8. Are mode-specific temporal behaviors and GPS noise recorded as assumptions? | YES |
| Q9. Are multimodal transfers spatially validated? | YES |
| Q10. Did the full dataset pass independent validation with zero failures? | YES |
| Q11. Does the dataset contain exactly 700 journeys with all required categories? | YES |
| Q12. Is the evaluation package frozen with hashes and ready for delivery? | YES |

## Full Run

The full candidate was generated with seed 42026 and contains 700 journeys:
120 walk, 110 bike, 110 car, 100 bus, 120 rail, and 140 multimodal.

The independent validator passed 4,672 of 4,672 checks with zero failures.
The independent artifact audit passed manifest count, GPS and Ground Truth
count, validation status, and reference manifest presence checks.

Validation artifacts are written under the candidate `validation` directory:
the overall JSON report, one CSV for each mode, geometry and physical CSVs,
and the multimodal transfer CSV.

The reference acquisition gate is recorded in
`REFERENCE_ACQUISITION_GATE.md`. It records PASS for all five implemented
modes. Of the 718 official bus route records, 55 have complete routable
geometry in the candidate catalog and 663 are explicitly excluded as failed
routes. Excluded routes were not generated through a fallback.

The final freeze records the generator commit, reference manifest hash,
configuration hash, validation result, and file hashes. The exported package
is `output/evaluation_dataset_v2`.
