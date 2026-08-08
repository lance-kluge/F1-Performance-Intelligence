# F1 Performance Intelligence

F1 Performance Intelligence is a typed, local-first Python foundation for Formula 1
performance analysis. Milestone 1 ingests complete FastF1 sessions, normalizes them into
stable pandas schemas, writes immutable Parquet snapshots, and uses SQLite to select the
active snapshot.

The package is intentionally headless. Driver analysis, tire modeling, strategy simulation,
Streamlit, and the race-engineer interface will build on these contracts in later milestones.

## Setup

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

`pyproject.toml` is the dependency source of truth. `requirements.txt` is a generated,
runtime-only compatibility export.

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

print(result.cache_hit)
print(race.results().sort_values("position").head())
print(race.car_telemetry("LEC").head())
```

The first native or ingestion load can take several minutes because FastF1 retrieves and
processes the session. FastF1's request cache accelerates later native loads. Repeated ingestion
calls return the active normalized snapshot without invoking FastF1 at all.

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
pytest -m live tests/test_live_bahrain.py --no-cov
```

It ingests the 2022 Bahrain Grand Prix Race, verifies Charles Leclerc as the winner, reads all
core datasets, demonstrates a local cache hit, and exercises a forced refresh.

See [architecture](docs/architecture.md) and [schema reference](docs/schemas.md) for the
platform boundaries and normalized units.

## Data and trademarks

FastF1 is an unofficial client and is not associated with the Formula 1 companies. Formula 1
and related marks belong to their respective owners. Users are responsible for ensuring their
use and redistribution of upstream data complies with applicable terms and law. This project
does not redistribute FastF1 session data in Git.
