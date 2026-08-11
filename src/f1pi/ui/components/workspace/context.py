"""Session and comparison context panels for the workspace."""

from __future__ import annotations

from html import escape

import streamlit as st

from f1pi.analysis.models import LapComparison
from f1pi.domain.models import ScheduledEvent, ScheduledSession
from f1pi.ui.models import LoadedSession


def render_session_context(event: ScheduledEvent, session: ScheduledSession) -> None:
    """Summarize the pending load and explain its local-first behavior."""
    st.html(
        f"""
        <aside class="f1pi-session-context" aria-label="Selected session">
          <div><span>Selected session</span>
            <strong>{escape(event.event_name)} · {escape(session.name)}</strong>
            <small>Round {event.round_number} · {escape(event.location)} ·
              {session.starts_at_utc:%d %b %Y, %H:%M UTC}</small></div>
          <p><b>Local-first</b> Existing snapshots load immediately. A first-time session may
          take a few minutes while FastF1 telemetry is retrieved and normalized.</p>
        </aside>
        """
    )


def render_loaded_session(loaded: LoadedSession) -> None:
    """Confirm the loaded snapshot with useful selection context."""
    lap_count = sum(len(driver.accurate_lap_numbers) for driver in loaded.drivers)
    source = "Local snapshot reused" if loaded.snapshot_reused else "New snapshot prepared"
    st.html(
        f"""
        <aside class="f1pi-session-ready" aria-label="Loaded session">
          <span class="f1pi-session-ready__icon" aria-hidden="true">✓</span>
          <div><span>Session ready</span>
            <strong>{escape(loaded.metadata.event_name)} ·
              {escape(loaded.metadata.session_name)}</strong>
            <small>{len(loaded.drivers)} drivers · {lap_count} accurate timed laps</small></div>
          <span class="f1pi-session-ready__source">{escape(source)}</span>
        </aside>
        """
    )


def render_comparison_ready(comparison: LapComparison) -> None:
    """Confirm which durable comparison is being shown below the controls."""
    st.html(
        f"""
        <aside class="f1pi-comparison-ready" aria-label="Current comparison">
          <div><span>Current analysis</span><strong>{escape(comparison.lap_a.driver)}
            <small>lap {comparison.lap_a.lap_number}</small><i>versus</i>
            {escape(comparison.lap_b.driver)} <small>lap {comparison.lap_b.lap_number}</small>
          </strong></div>
          <span>Change a selection above and compare again to replace these results.</span>
        </aside>
        """
    )
