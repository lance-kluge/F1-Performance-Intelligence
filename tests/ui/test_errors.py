from __future__ import annotations

import pytest

from f1pi.domain.exceptions import (
    IncompatibleSchemaError,
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
