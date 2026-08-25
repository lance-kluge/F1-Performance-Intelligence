"""User-safe error translation for the analysis workspace."""

from __future__ import annotations

from dataclasses import dataclass

from f1pi.domain.exceptions import (
    IncompatibleSchemaError,
    InsufficientTireDataError,
    InvalidSessionError,
    LapNotFoundError,
    StorageError,
    TelemetryNotAvailableError,
    UnsupportedTireSessionError,
    UpstreamRateLimitError,
    UpstreamUnavailableError,
)


@dataclass(frozen=True, slots=True)
class UserError:
    title: str
    detail: str


def user_error(error: Exception) -> UserError:
    if isinstance(error, UpstreamRateLimitError):
        return UserError(
            "FastF1 is busy",
            "Wait a few minutes, then try loading the session again.",
        )
    if isinstance(error, UpstreamUnavailableError):
        return UserError(
            "Session data is unavailable",
            "Check your connection or choose another completed session, then try again.",
        )
    if isinstance(error, InvalidSessionError):
        return UserError("Invalid session", "Choose another event or session from the schedule.")
    if isinstance(error, LapNotFoundError):
        return UserError(
            "Lap not available",
            "Choose another accurate timed lap and compare again.",
        )
    if isinstance(error, TelemetryNotAvailableError):
        return UserError(
            "Telemetry is incomplete",
            "One selected lap does not contain enough telemetry for a full comparison.",
        )
    if isinstance(error, UnsupportedTireSessionError):
        return UserError(
            "Session cannot be modeled",
            "Choose a completed Race or Sprint session for stint-based tire analysis.",
        )
    if isinstance(error, InsufficientTireDataError):
        return UserError(
            "Not enough clean tire data",
            "Choose another Race or Sprint. The model needs multiple clean stints for at "
            "least one compound.",
        )
    if isinstance(error, IncompatibleSchemaError):
        return UserError(
            "Stored data needs refreshing",
            "Reload the session to rebuild it with the current analytical schema.",
        )
    if isinstance(error, StorageError):
        return UserError(
            "Local data could not be read",
            "Reload the session. The previous successful snapshot remains protected.",
        )
    return UserError(
        "Analysis could not be completed",
        "Try the operation again. If it continues to fail, inspect the local application log.",
    )
