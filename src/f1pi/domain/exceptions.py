"""Stable application exceptions."""


class F1PIError(Exception):
    """Base class for platform failures."""


class InvalidSessionError(F1PIError):
    """The requested event or session identifier is invalid."""


class UpstreamUnavailableError(F1PIError):
    """The upstream session data is not currently available."""


class UpstreamRateLimitError(UpstreamUnavailableError):
    """FastF1 rejected the request because a hard rate limit was reached."""


class SchemaValidationError(F1PIError):
    """A normalized dataset does not satisfy the platform schema."""


class StorageError(F1PIError):
    """A dataset or catalog operation failed."""


class SessionNotInStoreError(StorageError):
    """No successful local ingestion exists for the session."""


class DatasetNotAvailableError(StorageError):
    """The requested dataset was not included in the ingestion."""


class IncompatibleSchemaError(StorageError):
    """A stored snapshot uses a schema version this package cannot read."""


class LapAnalysisError(F1PIError):
    """A lap comparison cannot be completed from the available session data."""


class LapNotFoundError(LapAnalysisError):
    """A requested or eligible lap is not available."""


class TelemetryNotAvailableError(LapAnalysisError):
    """A selected lap does not have enough telemetry for comparison."""


class TireModelError(F1PIError):
    """Tire degradation cannot be modeled from the requested session."""


class UnsupportedTireSessionError(TireModelError):
    """The session type does not support stint-based tire modeling."""


class DriverNotFoundError(TireModelError):
    """The requested driver is not present in the session laps."""


class InsufficientTireDataError(TireModelError):
    """No compound has enough clean, identifiable data for a tire model."""


class StrategySimulationError(F1PIError):
    """A strategy counterfactual cannot be simulated."""


class UnsupportedStrategySessionError(StrategySimulationError):
    """The requested session cannot be used for strategy simulation."""


class InvalidStrategyError(StrategySimulationError):
    """A strategy request contains contradictory or impossible instructions."""


class InsufficientStrategyDataError(StrategySimulationError):
    """The session does not contain enough information to calibrate the simulator."""
