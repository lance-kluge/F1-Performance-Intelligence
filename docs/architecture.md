# Architecture

## Dependency direction

The domain contains immutable identifiers and result records. Protocols define the three
external boundaries: session source, dataset store, and catalog. The ingestion service depends
only on those protocols. Concrete FastF1, Parquet, and SQLite adapters point inward toward the
contracts.

```text
Caller
  │
  ├── FastF1Client.load ─────────────────────────── native FastF1 Session
  │
  ├── IngestionService ── SessionSource protocol ── FastF1Client.fetch
  │         │
  │         ├──────────── DatasetStore protocol ─── Parquet adapter
  │         └──────────── Catalog protocol ───────── SQLite adapter
  │
  └── SessionRepository ──────────────────────────── typed DataFrames
            │
            └── LapAnalysisService ── LapComparisonEngine ── chart-ready comparison
```

Native FastF1 `Session`, `Laps`, `Lap`, and `Telemetry` objects are intentionally available
through `platform.fastf1` for analysis and exploration.

## Package layout

```text
src/f1pi/
├── domain/          immutable models and application errors
├── application/     use cases, repositories, and boundary protocols
├── processing/      normalization and versioned dataset schemas
├── infrastructure/  FastF1, Parquet, SQLite, and logging adapters
├── config.py        environment-backed platform settings
└── composition.py   concrete dependency wiring
```

The `tests/` tree mirrors these package boundaries. End-to-end checks that cross every layer
live under `tests/integration/`. Future analysis, simulation, and interface packages can be
added beside these layers without mixing their code into the ingestion foundation.

The persistence path is separate: `FastF1Client.fetch` detaches plain pandas frames, which are
normalized and validated by versioned Pandera models before storage. Stored datasets never retain
a FastF1 session reference. The design avoids converting millions of telemetry rows into Python
object graphs of our own.

## Ingestion transaction

Each attempt receives an ingestion run ID. Normalized frames are validated before being
written beneath a staging directory. The complete staging directory is renamed to an immutable
run directory on the same filesystem. One SQLite transaction then records every artifact and
changes the session's active run.

If validation or Parquet publication fails, no catalog session is created. If the catalog
transaction fails after publication, the unpublished run directory is removed. Rebuilding or
refreshing therefore cannot damage the previously active snapshot.

Session aliases preserve the request form used by callers. A first request using an event name
and another using its round number may require separate upstream resolution, but both resolve to
the same canonical session ID and active snapshot thereafter.

## Cache and snapshot ownership

- FastF1 cache: upstream HTTP responses and parsed API data, managed by `fastf1.Cache`.
- Parquet snapshots: normalized analytical data, immutable per ingestion run.
- SQLite catalog: aliases, canonical session metadata, run history, active-run pointer, artifact
  locations, and row counts. It does not duplicate analytical rows.

The Parquet layer is a materialized analytical store, not a second upstream cache. A catalog
snapshot is reused only when every artifact exists and its dataset kinds satisfy the current
`LoadOptions`. Full snapshots can serve partial requests; requests for telemetry, weather, or
messages automatically rebuild an active snapshot that omitted those datasets.

`rebuild_snapshot=True` bypasses the active Parquet snapshot but allows FastF1 to use its cache.
`refresh_upstream=True` also bypasses the snapshot and configures FastF1 with `force_renew=True`,
causing FastF1 to ignore and renew its cached upstream data.

Car and position telemetry remain separate. FastF1 documents that combined telemetry includes
interpolated values; lap alignment and derived distance therefore belong to the analysis layer.

## Future milestones

Tire degradation, strategy simulation, and future analytical services can follow the lap
analyzer's split: an application service resolves a snapshot, a presentation-neutral engine owns
the calculation, and immutable result records define the handoff to interfaces. They should obtain
native sessions through `FastF1Client`, not configure FastF1 caches independently or infer schemas
from raw cache files.
