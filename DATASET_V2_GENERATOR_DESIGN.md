# Dataset v2 Generator Design

Dataset v2 is an independent generator for an independently developed
platform. The generator does not read predictions from an external mobility
classifier.

The pipeline is ordered as follows:

1. Select a validated real reference route.
2. Build a true trajectory by resampling the actual route polyline.
3. Simulate mode-specific speed, acceleration, stop dwell, and time behavior.
4. Create a separate GPS observation with explicit noise and accuracy fields.
5. Write Ground Truth separately from GPS.
6. Run geometry, physical, timestamp, transfer, and file contract validation.

Rail uses OSM railway relation and way geometry. Bus uses official Seoul stop
sequence records and actual local road graph paths for every included route.
Car, walk, and bike each use a separate local graph and profile. A route is
rejected when required geometry or a connected path is unavailable. There is
no straight-line fallback, arbitrary coordinate fallback, fabricated station
sequence, or cross-mode graph reuse.

The nominal GPS interval is 4.8 to 6.8 seconds. Coordinate noise, accuracy,
speed noise, course noise, and missing-fix probabilities are recorded in
`config/mobility_parameter_manifest.json`. The values are declared simulation
assumptions and are not claims about measured phone or traffic traces.

The generated true trajectory is kept under `true_trajectories` for audit.
The evaluation export excludes that development material and contains only
GPS, Ground Truth, manifests, freeze metadata, and validation report.
