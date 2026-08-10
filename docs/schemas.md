# Schema reference — version 2

All tables use stable `snake_case` names and contain `session_id`. Pandera permits additional
upstream columns after their names and physical types are normalized, while enforcing the
columns required by downstream contracts.

## Units and physical representation

- Durations end in `_ns` and use nullable signed 64-bit integer nanoseconds.
- Absolute timestamps end in `_utc_ns` and use nullable signed 64-bit nanoseconds since the Unix
  epoch in UTC.
- Speed is kilometers per hour, RPM is revolutions per minute, throttle is percent, weather
  temperatures are degrees Celsius, pressure is mbar, wind speed is meters per second, and
  position coordinates retain FastF1's coordinate units.
- Identifiers and categorical values use pandas' nullable string dtype.
- Boolean channels use pandas' nullable boolean dtype.
- Discrete numeric channels (positions, lap and stint numbers, wind direction, telemetry,
  and position coordinates) use pandas' nullable signed 64-bit integer dtype so missing values
  do not force integer measurements to floating point.

## Datasets

- `session`: canonical event/session metadata, FastF1 version, and schema version.
- `results`: driver identity, constructor, finishing position, and status.
- `laps`: driver/lap identity, lap and sector times, lap start time, stint, compound, tire life,
  freshness, and accuracy.
- `weather`: session time and ambient measurements.
- `car_telemetry`: driver-partitioned speed, RPM, gear, throttle, brake, and DRS samples.
- `position`: driver-partitioned track coordinates and sample status.
- `circuit_corners`: optional turn labels and coordinates used to annotate track comparisons.
- `track_status`: flag/status changes over session time.
- `session_status`: lifecycle changes over session time.
- `race_control`: messages and any accompanying category, flag, scope, or sector fields.

Adding or changing required semantics increments `schema_version`; readers never silently treat a
snapshot from another version as current.

Snapshots written with an earlier schema are not opened by the repository. Calling ingestion for
the same session rebuilds the snapshot with the current schema while preserving the previous
immutable run.

### Throttle sentinel

FastF1 documents the upstream throttle value `104` as an error or unavailable-data sentinel,
usually observed while a car is stationary in the pits or on the grid. `throttle_raw` preserves
the upstream value (`0–104`). The analytical `throttle` column is a nullable percentage (`0–100`)
and represents `104` as `NA`. Other out-of-range values fail schema validation.
