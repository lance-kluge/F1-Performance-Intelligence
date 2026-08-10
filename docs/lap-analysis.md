# Lap analysis methodology

The lap analyzer is a backend use case over an immutable, normalized session snapshot. It does
not depend on FastF1's session-bound objects and does not contain chart or Streamlit concerns.

## Public contract

`LapAnalysisService.compare` accepts a `SessionKey` and two `LapSelection` values. A selection
without a lap number chooses the driver's quickest lap whose `is_accurate` flag is true. An
explicit lap number is deterministic and uses the same accuracy guard unless the caller opts out.

The returned `LapComparison` contains:

- selected-lap summaries and the overall signed delta;
- three signed sector comparisons;
- one spatially synchronized telemetry frame with speed, throttle, brake, elapsed time, position,
  sector, and live time delta columns;
- comparisons for every available circuit corner; and
- a structured `LapExplanation` plus display-ready text.

All signed deltas use `lap B - lap A`. A positive value means lap A is ahead or faster over that
interval. Driver names remain outside telemetry column names so consumers can use a stable chart
schema and obtain display labels from `lap_a` and `lap_b`.

## Synchronization and delta

Each selected lap is cut from driver-partitioned car and position data using its persisted
`lap_start_time_ns` and `lap_time_ns`. Exact start and finish samples are interpolated when the
upstream sample clocks do not land on those boundaries.

Distance is reconstructed by trapezoidal integration of speed over time. Both laps are then
interpolated onto the same configurable 0–100% spatial grid. This avoids comparing channels at
equal elapsed time, which would align different places on track as soon as one driver gains time.
The live delta at each spatial sample is:

```text
elapsed time for lap B - elapsed time for lap A
```

The first value is zero and the finish value matches the overall lap-time difference. The
`distance_metres` axis uses lap A as the reference; `relative_distance` is invariant to small
differences in reconstructed path length.

## Track and corner evidence

Position channels are interpolated onto the same spatial grid, retaining coordinates for both
drivers. Optional FastF1 circuit metadata supplies turn numbers. Each marker is located on lap A's
measured path by nearest X/Y coordinate rather than trusting marker distance from a different
reference lap.

For every corner, the analyzer measures local delta change and minimum speed in a configurable
window. It also finds the first post-corner sample at or above the configured full-throttle
threshold. The explanation selects the sector and corner with the largest positive loss for the
slower driver, then mentions minimum-speed and throttle differences only when the measurements
support those claims. If corner metadata is unavailable, sector and overall explanations still
work and the `corners` result is empty.

These are comparative observations, not claims about driver intent or vehicle causality. Weather,
traffic, tire state, energy deployment, and setup can all contribute to an observed difference.
