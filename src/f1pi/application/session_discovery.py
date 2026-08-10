"""Discover completed, telemetry-capable race-weekend sessions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from f1pi.application.ports import EventScheduleSource
from f1pi.domain.models import ScheduledEvent

SESSION_COMPLETION_DELAY = timedelta(hours=4)


class SessionDiscoveryService:
    def __init__(self, source: EventScheduleSource) -> None:
        self._source = source

    def list_available_events(
        self,
        year: int,
        *,
        as_of_utc: datetime | None = None,
    ) -> tuple[ScheduledEvent, ...]:
        """Return events with at least one conservatively completed session."""
        cutoff = as_of_utc or datetime.now(UTC)
        cutoff = (
            cutoff.replace(tzinfo=UTC)
            if cutoff.tzinfo is None
            else cutoff.astimezone(UTC)
        )

        available: list[ScheduledEvent] = []
        for event in self._source.events(year):
            completed = tuple(
                session
                for session in event.sessions
                if session.starts_at_utc + SESSION_COMPLETION_DELAY <= cutoff
            )
            if completed:
                available.append(
                    ScheduledEvent(
                        year=event.year,
                        round_number=event.round_number,
                        event_name=event.event_name,
                        country=event.country,
                        location=event.location,
                        sessions=completed,
                    )
                )
        return tuple(available)
