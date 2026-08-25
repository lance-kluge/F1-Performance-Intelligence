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


class InsufficientTireDataError(TireModelError):
    """No compound has enough clean, identifiable data for a tire model."""
