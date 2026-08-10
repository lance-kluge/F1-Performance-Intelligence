"""F1 Performance Intelligence data foundation."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from f1pi.analysis import LapComparison, LapSelection, SynchronizationConfig
    from f1pi.composition import Platform, build_platform
    from f1pi.config import PlatformSettings
    from f1pi.domain import (
        IngestionResult,
        LoadOptions,
        ScheduledEvent,
        ScheduledSession,
        SessionKey,
        SessionType,
    )
    from f1pi.infrastructure.fastf1_client import FastF1Client

__all__ = [
    "FastF1Client",
    "IngestionResult",
    "LapComparison",
    "LapSelection",
    "LoadOptions",
    "Platform",
    "PlatformSettings",
    "ScheduledEvent",
    "ScheduledSession",
    "SessionKey",
    "SessionType",
    "SynchronizationConfig",
    "build_platform",
]

_EXPORTS = {
    "FastF1Client": ("f1pi.infrastructure.fastf1_client", "FastF1Client"),
    "IngestionResult": ("f1pi.domain", "IngestionResult"),
    "LapComparison": ("f1pi.analysis", "LapComparison"),
    "LapSelection": ("f1pi.analysis", "LapSelection"),
    "LoadOptions": ("f1pi.domain", "LoadOptions"),
    "Platform": ("f1pi.composition", "Platform"),
    "PlatformSettings": ("f1pi.config", "PlatformSettings"),
    "ScheduledEvent": ("f1pi.domain", "ScheduledEvent"),
    "ScheduledSession": ("f1pi.domain", "ScheduledSession"),
    "SessionKey": ("f1pi.domain", "SessionKey"),
    "SessionType": ("f1pi.domain", "SessionType"),
    "SynchronizationConfig": ("f1pi.analysis", "SynchronizationConfig"),
    "build_platform": ("f1pi.composition", "build_platform"),
}


def __getattr__(name: str) -> object:
    """Load public package exports only when callers request them."""
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error

    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazy public exports to interactive tooling."""
    return sorted({*globals(), *__all__})
