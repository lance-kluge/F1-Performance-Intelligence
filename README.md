# F1 Performance Intelligence

F1 Performance Intelligence is a typed, local-first Python foundation for Formula 1
performance analysis. It ingests complete FastF1 sessions, normalizes them into stable pandas
schemas, writes immutable Parquet snapshots, and uses SQLite to select the active snapshot.
The headless lap analyzer returns synchronized telemetry, track coordinates, exact section and
corner-phase attribution, quality metadata, and an evidence-backed performance summary. The tire
backend extracts clean Race and Sprint stints and returns validated compound degradation curves
with confidence and prediction intervals.

The analytical package is presentation-neutral. A Streamlit interface builds on these contracts
without owning analytical logic; strategy simulation and the race-engineer interface remain
future work.

## Setup

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,ui]'
```

`pyproject.toml` is the dependency source of truth. `requirements.txt` is a generated,
runtime-only compatibility export.

## Web application

Run the local Streamlit interface from the repository root:

```bash
streamlit run streamlit_app.py
```

The landing experience is intentionally independent of FastF1 and the local data store, so it
starts without downloading a session. Analysis workspaces load data only after a user asks for a
specific event and session.

In **Lap analysis**, choose a season, race weekend, and completed session. The first load retrieves
and normalizes FastF1 telemetry; later loads reuse the immutable local snapshot. Each driver can
use their fastest accurate lap or an exact accurate lap number. Results include sector deltas, a
circuit trace, the live time delta, speed, throttle and brake channels, corner losses, and the
evidence-backed explanation returned by the analytical service.

In **Tire degradation**, choose a completed Race or Sprint and run the recommended
condition-adjusted model or inspect the raw lap-time trend. Results lead with compound degradation
rates and their uncertainty, then expose modeled curves, whole-stint validation, lap eligibility,
and the stable stints behind the fit. Existing snapshots are reused and telemetry is not loaded.

## Quick start

Use native FastF1 objects for interactive and analytical work:

```python
from f1pi import SessionKey, build_platform

platform = build_platform()
key = SessionKey(2022, "Bahrain", "R")
session = platform.fastf1.load(key)

fastest = session.laps.pick_drivers("LEC").pick_fastest()
telemetry = fastest.get_car_data()
```

Use ingestion and the repository when the session must be normalized, persisted, and available
offline:

```python
from f1pi import SessionKey, build_platform

platform = build_platform()
key = SessionKey(2022, "Bahrain", "R")

result = platform.ingestion.ingest(key)
race = platform.sessions.open(key)

print(result.snapshot_reused)
print(race.results().sort_values("position").head())
print(race.car_telemetry("LEC").head())
```

The first native or ingestion load can take several minutes because FastF1 retrieves and
processes the session. FastF1's request cache accelerates later native loads. Repeated ingestion
calls reuse the active normalized snapshot without invoking FastF1 at all.

Compare the fastest accurate laps for two drivers:

```python
from f1pi import LapSelection, SessionKey, build_platform

platform = build_platform()
key = SessionKey(2026, "Monaco", "Q")

comparison = platform.lap_analysis.compare(
    key,
    LapSelection.fastest("NOR"),
    LapSelection.fastest("VER"),
)

print(comparison.delta_seconds)  # lap B - lap A
print(comparison.explanation.text)
print(comparison.telemetry.head())  # speed, inputs, track, and live delta
print(comparison.summary.findings)  # structured losses, gains, and supporting evidence
print(comparison.sections)  # non-overlapping corner complexes and straights
```

`comparison.sections` covers the complete lap exactly once. Its signed section deltas reconcile
to the finish delta, while corner complexes expose entry, apex, and exit attribution plus
per-driver metrics. `comparison.quality` identifies telemetry-only segmentation, missing optional
channels, and any degraded result. The earlier `corners`, `straights`, and `explanation` fields
remain available for compatible consumers.

Use `LapSelection.numbered("NOR", 12)` to compare an explicit lap. Selections reject laps FastF1
marks inaccurate by default; pass `accurate_only=False` when an inaccurate numbered lap is
intentional.

Analyze tire degradation from an ingested Race or Sprint snapshot:

```python
from f1pi import DegradationMode, SessionKey, TireModelConfig, build_platform

platform = build_platform()
key = SessionKey(2022, "Bahrain", "R")
platform.ingestion.ingest(key)

adjusted = platform.tire_model.analyze(key)
raw = platform.tire_model.analyze(key, TireModelConfig(mode=DegradationMode.RAW))
leclerc = platform.tire_model.analyze_driver(key, "LEC")

print(adjusted.estimates)  # compound rates and 95% confidence intervals
print(adjusted.curves.head())  # chart-ready mean and individual-lap bands
print(leclerc.observations.head())  # selected-driver laps only
```

Adjusted mode controls for driver, race progress, and changing weather. Raw mode exposes the
unadjusted within-session trend. Both are associations from observed clean laps and do not claim
that tire age caused every recorded lap-time change. Individual-driver analysis uses the same
pipeline with driver-appropriate support thresholds; validation is `None` when whole-stint
cross-validation is not possible.

Snapshot and upstream refreshes are deliberately separate:

```python
from f1pi import LoadOptions

# Re-normalize and republish using FastF1's cache where possible.
platform.ingestion.ingest(key, LoadOptions(rebuild_snapshot=True))

# Also tell FastF1 to ignore and renew its cached upstream data.
platform.ingestion.ingest(key, LoadOptions(refresh_upstream=True))
```

## Configuration

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `F1PI_DATA_DIR` | `./data` | Catalog and normalized dataset root |
| `F1PI_FASTF1_CACHE_DIR` | `$F1PI_DATA_DIR/cache/fastf1` | FastF1 HTTP/API cache |
| `F1PI_LOG_LEVEL` | `INFO` | Structured application log level |

FastF1 owns the raw request cache. F1PI owns the normalized Parquet snapshots and SQLite
catalog. Deleting the FastF1 cache causes upstream data to be downloaded again; deleting an
F1PI snapshot makes that session unavailable to the analytical layer.

## Quality checks

```bash
ruff check .
mypy src
pytest
```

The network acceptance test is intentionally excluded from normal CI:

```bash
pytest -m live tests/integration/test_live_bahrain.py --no-cov
```

It ingests the 2022 Bahrain Grand Prix Race, verifies Charles Leclerc as the winner, reads all
core datasets, demonstrates snapshot reuse, and exercises an upstream refresh.

See [architecture](docs/architecture.md), [lap analysis methodology](docs/lap-analysis.md),
[tire model methodology](docs/tire-model.md), and [schema reference](docs/schemas.md) for the
platform boundaries, analytical conventions, and normalized units.

## Data and trademarks

FastF1 is an unofficial client and is not associated with the Formula 1 companies. Formula 1
and related marks belong to their respective owners. Users are responsible for ensuring their
use and redistribution of upstream data complies with applicable terms and law. This project
does not redistribute FastF1 session data in Git.
