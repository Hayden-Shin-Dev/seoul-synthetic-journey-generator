# Validator Independence Audit

The independent module reads Frozen GPS, Frozen Ground Truth, package manifests, official bus XLSX, OSM-derived rail reference, and separate local mode graphs. It does not import or read the generator validator result. Mutation tests use temporary copies and never modify the Frozen package.

The point report uses external network proximity and observed timestamps. Empty true position columns indicate that the Frozen delivery package does not expose generator-side true samples; no generator validation artifact is used as a substitute.
