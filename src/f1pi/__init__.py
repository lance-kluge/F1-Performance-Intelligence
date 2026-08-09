"""F1 Performance Intelligence data foundation."""

from f1pi.composition import Platform, build_platform
from f1pi.config import PlatformSettings
from f1pi.domain import IngestionResult, LoadOptions, SessionKey, SessionType
from f1pi.infrastructure.fastf1_client import FastF1Client

__all__ = [
    "FastF1Client",
    "IngestionResult",
    "LoadOptions",
    "Platform",
    "PlatformSettings",
    "SessionKey",
    "SessionType",
    "build_platform",
]
