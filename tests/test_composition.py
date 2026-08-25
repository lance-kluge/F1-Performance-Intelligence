from pathlib import Path

from f1pi.application.repository import SessionRepository
from f1pi.application.session_discovery import SessionDiscoveryService
from f1pi.application.tire_model import TireModelService
from f1pi.composition import build_platform
from f1pi.config import PlatformSettings
from f1pi.infrastructure.fastf1_client import FastF1Client


def test_platform_factory(tmp_path: Path) -> None:
    settings = PlatformSettings(tmp_path / "data", tmp_path / "cache")
    platform = build_platform(settings)
    assert isinstance(platform.fastf1, FastF1Client)
    assert isinstance(platform.sessions, SessionRepository)
    assert isinstance(platform.session_discovery, SessionDiscoveryService)
    assert isinstance(platform.tire_model, TireModelService)
    assert settings.processed_dir == tmp_path / "data" / "processed"
