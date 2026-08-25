# Tire degradation methodology

The tire model is a backend use case over one immutable Race or Sprint snapshot. It depends on
normalized laps, weather, and track-status events; it does not read telemetry, call FastF1, persist
derived artifacts, or contain chart and Streamlit concerns.

## Public contract

`TireModelService.analyze` accepts a `SessionKey` and optional `TireModelConfig`. Adjusted mode is
the default; raw mode is available for a future UI toggle. The returned `TireDegradationAnalysis`
contains immutable stint summaries, compound degradation estimates, grouped validation metrics,
machine-readable warnings, and two stable DataFrames:

- `observations` contains every lap, its stint and condition features, eligibility decision,
  exclusion reason, fitted value, and residual;
- `curves` contains one in-support curve per modeled compound with a mean confidence band and a
  wider individual-lap prediction band.

Curves never extend beyond the minimum and maximum tire age observed for their compound.

`TireModelService.analyze_driver` accepts a `SessionKey`, driver abbreviation, and optional
`DriverTireModelConfig`. It runs the same preparation, regression, uncertainty, and curve pipeline
after selecting that driver's rows. The returned `DriverTireDegradationAnalysis` is self-describing
through its canonical `driver` value, and its stints and observations never contain another
driver. Full-session preparation happens before selection so race progress retains the session's
actual lap range, including when the selected driver retires early.

Driver defaults allow a compound supported by one physical stint and five clean laps. Session-wide
defaults still require two stints and eight laps. A single-stint driver estimate is marked with a
`single_stint_estimate:<compound>` warning rather than being presented as equivalent to a pooled,
repeated-stint estimate.

## Stints and clean laps

Upstream stint numbers are respected, but a new stable stint starts whenever the driver changes
compound, skips a lap number, or reports a lower tire age. `tire_age_laps` preserves FastF1's tire
life, including used sets that begin above age one; `stint_lap_index` separately counts the laps
observed in that stint.

Each lap receives at most one primary exclusion reason, in deterministic order. Missing or
inaccurate timing rows, deleted laps, pit in/out laps, non-green track-status overlaps, missing
adjusted features, laps more than the configured ratio above that driver's quickest clean lap on
the same compound, and undersized stints are excluded. Excluded rows remain in `observations` for
auditing.

Weather is averaged over the lap interval, with the nearest midpoint sample used when no weather
sample falls inside the interval. Race progress is normalized from zero to one and acts as a fuel
load and track-evolution proxy. Condition columns with no within-session variation are omitted and
reported as warnings.

## Regression and uncertainty

One pooled ordinary least-squares design contains a separate intercept and linear tire-age slope
for every supported compound. Raw mode uses only those terms. Adjusted mode adds driver fixed
effects, race progress, track and air temperature, humidity, pressure, wind speed, and rainfall.
Redundant columns are dropped deterministically rather than fitting a rank-deficient design.

The reported seconds-per-lap estimate is the compound's tire-age coefficient. Coefficient
confidence uses covariance clustered by physical stint. Curve confidence bands describe
uncertainty in the fitted mean; prediction bands additionally include residual lap-to-lap
variation. Adjusted compound curves average over observed drivers and hold changing conditions at
that compound's median values.

Driver-scoped curves use only the selected driver's fitted design. With one driver and one stint
per compound, tire age can be collinear with race progress; the existing deterministic design
selection drops the redundant condition and reports it. Such a result is a within-stint trend, not
evidence that fuel load and track evolution were independently identified.

## Validation and limitations

Cross-validation assigns whole stints to folds, preventing laps from one stint from appearing in
both training and validation data. Up to five deterministic folds report MAE, RMSE, R², and the
MAE of a training-compound-mean baseline overall and per compound.

Driver analysis preserves the same whole-stint rule. When independent stints cannot produce a
valid held-out fit, `validation` is `None` and warnings include
`validation_unavailable:insufficient_independent_stints`. The model never substitutes random
lap-level folds. Multiple stints use stint-clustered covariance; a model containing only one stint
uses the existing HC3 covariance fallback and reports `cluster_covariance_unavailable`.

The model estimates conditional associations within one session. Race progress is only a proxy
for fuel burn and track evolution, while traffic, energy deployment, damage, setup, and driver
intent are not directly observed. Wet and intermediate tires use the same pipeline but are only
reported when they independently meet the configured lap and stint thresholds.
