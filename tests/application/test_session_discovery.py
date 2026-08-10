from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

from f1pi.application.ports import EventScheduleSource
from f1pi.application.session_discovery import SessionDiscoveryService
from f1pi.domain.models import ScheduledEvent, ScheduledSession, SessionType


def test_discovery_returns_only_events_with_started_sessions() -> None:
    source = Mock(spec=EventScheduleSource)
    source.events.return_value = (
        ScheduledEvent(
            2026,
            1,
            "Australian Grand Prix",
            "Australia",
            "Melbourne",
            (
                ScheduledSession(
                    SessionType.QUALIFYING,
                    "Qualifying",
                    datetime(2026, 3, 7, 5, tzinfo=UTC),
                ),
                ScheduledSession(
                    SessionType.RACE,
                    "Race",
                    datetime(2026, 3, 8, 4, tzinfo=UTC),
                ),
            ),
        ),
        ScheduledEvent(
            2026,
            2,
            "Chinese Grand Prix",
            "China",
            "Shanghai",
            (
                ScheduledSession(
                    SessionType.QUALIFYING,
                    "Qualifying",
                    datetime(2026, 3, 14, 7, tzinfo=UTC),
                ),
            ),
        ),
    )

    events = SessionDiscoveryService(source).list_available_events(
        2026, as_of_utc=datetime(2026, 3, 7, 12, tzinfo=UTC)
    )

    assert len(events) == 1
    assert events[0].event_name == "Australian Grand Prix"
    assert [session.name for session in events[0].sessions] == ["Qualifying"]
    source.events.assert_called_once_with(2026)


def test_discovery_treats_naive_cutoff_as_utc() -> None:
    source = Mock(spec=EventScheduleSource)
    source.events.return_value = (
        ScheduledEvent(
            2026,
            1,
            "Australian Grand Prix",
            "Australia",
            "Melbourne",
            (
                ScheduledSession(
                    SessionType.RACE,
                    "Race",
                    datetime(2026, 3, 8, 4, tzinfo=UTC),
                ),
            ),
        ),
    )

    events = SessionDiscoveryService(source).list_available_events(
        2026, as_of_utc=datetime(2026, 3, 8, 5)
    )

    assert len(events) == 1
