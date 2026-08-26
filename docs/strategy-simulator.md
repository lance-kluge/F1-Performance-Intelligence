# Strategy simulator methodology

The strategy simulator is a retrospective backend use case over one completed Race or Sprint
snapshot. It compares explicit future stop plans from a selected decision lap. It does not search
for an optimal strategy, forecast a future event, enforce sporting regulations, or persist fitted
models and random samples.

## Public contract

`StrategySimulationService.simulate` accepts a `SessionKey`, `StrategySimulationRequest`, and
optional `StrategySimulationConfig`. A request identifies the target driver, the last observed lap,
one or more named strategies, and one or more actual, green-race, or custom SC/VSC scenarios.
Candidate stops state the target lap after which the stop occurs, the next compound, and its
starting tire age.

The result contains the automatically reconstructed observed baseline, calibration diagnostics,
machine-readable warnings, paired Monte Carlo outcome samples, aggregate lap traces, and one
summary per scenario/strategy. Outcomes report position and time distributions; they do not
convert positions into points because scoring and classification rules change by season and
session type.

```python
from f1pi import (
    NeutralizationScenario,
    PlannedPitStop,
    SessionKey,
    StrategyPlan,
    StrategySimulationConfig,
    StrategySimulationRequest,
    build_platform,
)

platform = build_platform()
request = StrategySimulationRequest(
    driver="LEC",
    decision_lap=18,
    strategies=(
        StrategyPlan("undercut", (PlannedPitStop(20, "HARD"),)),
        StrategyPlan("extend", (PlannedPitStop(27, "HARD"),)),
    ),
    scenarios=(
        NeutralizationScenario.actual(),
        NeutralizationScenario.no_safety_car(),
    ),
)
analysis = platform.strategy_simulator.simulate(
    SessionKey(2026, "Monaco", "R"),
    request,
    StrategySimulationConfig(iterations=2_000, random_seed=7),
)
```

The application service expects a stored snapshot. A future UI should ingest with telemetry and
messages disabled and weather enabled before invoking it.

## Calibration

Calibration deliberately uses the complete race, so every result is a hindsight-calibrated
counterfactual rather than a claim about what was knowable on the decision lap.

- The existing adjusted tire regression supplies compound intercepts and degradation slopes,
  driver effects, race progress, and weather adjustment. It is fitted to accurate, green,
  non-pit clean-air laps. Sparse rival data may use traffic-contaminated laps and emits a warning;
  insufficient target data fails the request.
- Correlated regression coefficients are sampled from the fitted covariance. Remaining driver
  lap residuals are centered and bootstrapped.
- Pit loss is the excess observed time across consecutive pit-in and pit-out laps relative to the
  model's no-stop prediction. Samples use the empirical within-session distribution.
- Traffic loss is calibrated from positive pace residuals in four gap buckets up to the configured
  dirty-air threshold. Bucket medians are constrained not to increase as the gap grows.
- SC/VSC pace and pit-loss scaling are learned from the session. A custom event of a kind absent
  from the session must provide `NeutralizationAssumptions`; the simulator never inserts an
  undocumented circuit-independent fallback.

## Simulation

The engine reconstructs each car at the decision lap and carries the full field forward. Rivals
retain their observed compound and stop sequence, while the target's remaining sequence is
replaced by each candidate. Classified finishers continue to the scheduled distance; observed
retirement laps remain exogenous. Tire age advances each lap and resets to the value declared by a
pit stop.

At each lap, the engine samples clean pace, applies VSC/SC pace control or the current traffic
penalty, adds condition-adjusted pit loss, and reranks the field by completed distance and elapsed
time. VSC preserves the natural time gaps. SC suppresses normal traffic effects and compresses
same-lap gaps to the calibrated restart spacing. Custom scenarios replace the actual
neutralization schedule rather than merging with it.

One request-local NumPy generator produces coefficient, pace, traffic, and pit samples. The same
draws are reused for the baseline and every candidate, making their deltas paired and reproducible
for a fixed seed. Only aggregate lap quantiles and target outcome samples are returned, avoiding a
large full-field, per-iteration trace artifact.

## Limitations and failure behavior

The simulator requires laps, results, weather, and track status. Telemetry is not required. It
rejects non-race sessions, red-flag races, unclassified targets, decisions at or after the finish,
overlapping or historical custom windows, impossible stop timing, and candidate compounds without
calibrated support.

Traffic is a lap-resolution empirical penalty, not an overtaking agent. Mechanical failures are
not predicted, tire inventory and mandatory-compound legality are not checked, custom weather is
not simulated, and a retrospective calibration can benefit from information that was unavailable
to teams at the selected decision point. Warnings and diagnostics must be shown alongside results
so sparse fallbacks are not presented as equally supported estimates.
