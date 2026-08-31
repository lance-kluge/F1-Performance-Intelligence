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
- a complete partition of the lap into attributed corner complexes and straights;
- structured findings, quality metadata, and display-ready deterministic prose; and
- compatibility projections through `corners`, `straights`, and `LapExplanation`.

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

## Performance segmentation and attribution

Position channels are interpolated onto the same spatial grid, retaining coordinates for both
drivers. Optional FastF1 circuit metadata supplies turn numbers. Each marker is located on lap A's
measured path by nearest X/Y coordinate rather than trusting marker distance from a different
reference lap.

The analyzer builds an order-independent consensus speed trace from both laps. Official markers
anchor telemetry speed basins when available; otherwise prominent telemetry minima become
deterministically numbered detected corners. Entry and exit boundaries use sustained braking,
throttle lift, and full-throttle recovery, with speed maxima as channel-independent fallbacks.
Linked turns with no meaningful recovery are grouped into a corner complex while retaining their
individual apex metrics.

Corner complexes and the remaining straights form a non-overlapping circular partition, including
the start/finish straight. A section's signed attribution is the cumulative delta change at its
boundaries, so all section values telescope exactly to the finish delta. Each corner is partitioned
again into entry, apex-basin, and exit phases whose values reconcile to the parent complex.

Corner metrics include entry, minimum, and exit speed; the minimum-speed location; brake and
throttle events; full-throttle recovery; and minimum gear. Straight metrics include entry, exit,
average, and maximum speed. Optional channels produce nullable metrics and quality warnings rather
than failing an otherwise valid timing comparison.

## Automated summary contract

`ComparisonSummary` contains a headline, ranked structured findings, and narrative text. Findings
reference stable section IDs, the affected driver or lap, time magnitude, phase, confidence, and
the exact measurements that support their wording. The deterministic renderer reports the largest
losses and strongest offsetting gain above the configured noise floor.

`SummaryNarrativeProvider` is a narrow synchronous protocol for future narrative renderers. A
provider can rewrite prose from immutable findings but cannot modify attribution, evidence, or
quality. The composed platform uses the deterministic local renderer and performs no network call.

`AnalysisQuality` reports the segmentation source, available telemetry channels, categorical
confidence, reconciliation error, and machine-readable warnings. The analyzer only fails when
required speed or timing coverage cannot describe a complete lap.

These are comparative observations, not claims about driver intent or vehicle causality. Weather,
traffic, tire state, energy deployment, and setup can all contribute to an observed difference.

Narrative findings locate each turn complex or straight in its timing sector. Sections crossing
sector boundaries list every affected sector (including Sectors 3 and 1 at start/finish); the
reported section gain or loss remains the whole section's attribution, not a per-sector estimate.
