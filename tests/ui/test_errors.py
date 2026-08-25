from __future__ import annotations

import pytest

from f1pi.domain.exceptions import (
    IncompatibleSchemaError,
    InsufficientTireDataError,
    InvalidSessionError,
    LapNotFoundError,
    StorageError,
    TelemetryNotAvailableError,
    UpstreamRateLimitError,
    UpstreamUnavailableError,
)
from f1pi.ui.errors import user_error


@pytest.mark.parametrize(
    "error,title",
    [
        (UpstreamRateLimitError(), "FastF1 is busy"),
        (UpstreamUnavailableError(), "Session data is unavailable"),
        (InvalidSessionError(), "Invalid session"),
        (LapNotFoundError(), "Lap not available"),
        (TelemetryNotAvailableError(), "Telemetry is incomplete"),
        (IncompatibleSchemaError(), "Stored data needs refreshing"),
        (StorageError(), "Local data could not be read"),
        (RuntimeError(), "Analysis could not be completed"),
    ],
)
def test_errors_are_translated_to_safe_messages(error: Exception, title: str) -> None:
    assert user_error(error).title == title


@pytest.mark.parametrize(
    "detail,title,action",
    [
        (
            "weather is required for adjusted tire modeling",
            "Weather data is required",
            "raw model",
        ),
        (
            "track status is required for tire modeling",
            "Track-status data is required",
            "Reload the session",
        ),
        (
            "compound degradation slopes are not identifiable",
            "Tire trend could not be identified",
            "independent variation",
        ),
        (
            "no compound has enough clean laps and independent stints",
            "Not enough clean tire data",
            "multiple clean stints",
        ),
    ],
)
def test_tire_data_errors_preserve_actionable_cause(
    detail: str,
    title: str,
    action: str,
) -> None:
    translated = user_error(InsufficientTireDataError(detail))

    assert translated.title == title
    assert action in translated.detail
