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
```

Native FastF1 `Session`, `Laps`, `Lap`, and `Telemetry` objects are intentionally available
through `platform.fastf1` for analysis and exploration. This preserves FastF1's selection,
telemetry, and circuit helpers without duplicating their object model.

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
transaction fails after publication, the unpublished run directory is removed. A forced refresh
therefore cannot damage the previously active snapshot.

Session aliases preserve the request form used by callers. A first request using an event name
and another using its round number may require separate upstream resolution, but both resolve to
the same canonical session ID and active snapshot thereafter.

## Cache ownership

- FastF1 cache: upstream HTTP responses and parsed API data, managed by `fastf1.Cache`.
- Parquet snapshots: normalized analytical data, immutable per ingestion run.
- SQLite catalog: aliases, canonical session metadata, run history, active-run pointer, artifact
  locations, and row counts. It does not duplicate analytical rows.

Car and position telemetry remain separate. FastF1 documents that combined telemetry includes
interpolated values; lap alignment and derived distance therefore belong to the analysis layer.

## Future milestones

Driver comparison, tire degradation, strategy simulation, UI, and natural-language explanation
can use native FastF1 sessions for interactive calculations or `SessionRepository` for stable,
offline inputs. They should obtain native sessions through `FastF1Client`, not configure FastF1
caches independently or infer schemas from raw cache files.
