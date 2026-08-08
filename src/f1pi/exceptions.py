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

