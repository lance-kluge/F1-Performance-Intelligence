"""Top-level event, lap, and outcome summary."""

from __future__ import annotations

from html import escape

import streamlit as st

from f1pi.analysis.models import LapComparison
from f1pi.ui.formatting import comparison_outcome, format_delta, format_lap_time
from f1pi.ui.models import LoadedSession


def render_summary(session: LoadedSession, comparison: LapComparison) -> None:
    """Render the event and comparison outcome as a compact scoreboard."""
    winner, advantage = comparison_outcome(comparison)
    st.html(
        f"""
        <section class="f1pi-result-hero" aria-labelledby="result-title">
          <div class="f1pi-result-hero__event">
            <span>{session.metadata.year} · {escape(session.metadata.session_name)}</span>
            <h1 id="result-title">{escape(session.metadata.event_name)}</h1>
            <p>{escape(session.metadata.location)} · {escape(session.metadata.country)}</p>
          </div>
          <div class="f1pi-result-cards">
            {_lap_card("Driver A", comparison.lap_a.driver, comparison.lap_a.lap_number,
                       comparison.lap_a.lap_time_seconds, "a")}
            {_lap_card("Driver B", comparison.lap_b.driver, comparison.lap_b.lap_number,
                       comparison.lap_b.lap_time_seconds, "b")}
            <article class="f1pi-outcome-card"><span>Advantage</span>
              <strong>{escape(winner)}</strong><small>{escape(advantage)}</small>
              <em>{format_delta(comparison.delta_seconds)} · B - A</em></article>
          </div>
        </section>
        """
    )


def _lap_card(label: str, driver: str, number: int, seconds: float, variant: str) -> str:
    return f"""
    <article class="f1pi-result-lap f1pi-result-lap--{variant}">
      <span>{label}</span><strong>{escape(driver)}</strong>
      <small>Lap {number}</small><em>{format_lap_time(seconds)}</em>
    </article>
    """
