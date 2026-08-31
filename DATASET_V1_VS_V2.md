# Dataset v1 and v2

Dataset v1 remains unchanged and is retained for historical comparison only.
It used compact sampled corridors and did not contain complete independent
mode-specific local graphs or a complete official bus route catalog.

Dataset v2 uses the acquired Seoul PBF, official Seoul bus route and stop
files, local rail geometry, official stop sequences, and separate car, walk,
and bike graph artifacts. Every generated segment records its reference and
geometry method in Ground Truth.

The v1 output is not copied into v2 and is not used as a reference source for
the v2 evaluation package. The v2 package is generated with a new seed and is
validated and frozen independently.
