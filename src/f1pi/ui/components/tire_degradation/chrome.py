"""Headings and contextual chrome for the tire-analysis workflow."""

from __future__ import annotations

from html import escape

import streamlit as st

from f1pi.domain.models import ScheduledEvent, ScheduledSession
from f1pi.ui.models import TireAnalysisRun


def render_tire_intro() -> None:
    st.html(
        """
        <section class="f1pi-analysis-intro f1pi-tire-intro" aria-labelledby="tire-title">
          <div>
            <p class="f1pi-eyebrow"><span></span> Stint intelligence</p>
            <h1 id="tire-title">See how the tire changes the race.</h1>
          </div>
          <p>Estimate lap-time change as tires age, compare compounds on their observed support,
          and inspect the uncertainty behind every trend. Race data and snapshots stay local.</p>
        </section>
        """
    )


def render_tire_session_context(
    event: ScheduledEvent,
    session: ScheduledSession,
) -> None:
    st.html(
        f"""
        <aside class="f1pi-session-context" aria-label="Selected tire analysis session">
          <div><span>Selected session</span>
            <strong>{escape(event.event_name)} · {escape(session.name)}</strong>
            <small>Round {event.round_number} · {escape(event.location)} ·
              {session.starts_at_utc:%d %b %Y, %H:%M UTC}</small></div>
          <p><b>What is modeled</b> Clean green-flag laps from stable stints. Pit laps,
          deleted times, slow laps, and short stints remain visible in the audit view.</p>
        </aside>
        """
    )


def render_analysis_ready(run: TireAnalysisRun) -> None:
    analysis = run.analysis
    modeled_laps = int(analysis.observations["fitted_lap_time_seconds"].notna().sum())
    source = "Local snapshot reused" if run.snapshot_reused else "New snapshot prepared"
    st.html(
        f"""
        <aside class="f1pi-tire-ready" aria-label="Current tire analysis">
          <span class="f1pi-session-ready__icon" aria-hidden="true">✓</span>
          <div><span>Current analysis</span>
            <strong>{escape(analysis.metadata.event_name)} ·
              {escape(analysis.metadata.session_name)}</strong>
            <small>{len(analysis.estimates)} modeled compounds · {modeled_laps} modeled laps ·
              {analysis.validation.fold_count} validation folds</small></div>
          <span class="f1pi-session-ready__source">{escape(source)}</span>
        </aside>
        """
    )
