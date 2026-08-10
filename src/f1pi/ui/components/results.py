"""Result presentation composed from pure Plotly figure factories."""

from __future__ import annotations

from html import escape

import streamlit as st

from f1pi.analysis.models import LapComparison
from f1pi.ui.charts import (
    corner_loss_figure,
    delta_figure,
    inputs_figure,
    sector_figure,
    speed_figure,
    track_figure,
)
from f1pi.ui.formatting import comparison_outcome, format_delta, format_lap_time
from f1pi.ui.models import LoadedSession

PLOT_CONFIG = {"displayModeBar": False, "displaylogo": False, "responsive": True}


def render_results(session: LoadedSession, comparison: LapComparison) -> None:
    """Render the complete, ordered lap-comparison result."""
    _render_summary(session, comparison)

    st.html('<div class="f1pi-result-section"><span>01</span><h2>Sector comparison</h2></div>')
    st.plotly_chart(
        sector_figure(comparison),
        config=PLOT_CONFIG,
        width="stretch",
        key="sector_comparison",
    )

    st.html(
        '<div class="f1pi-result-section"><span>02</span>'
        "<h2>Where the time was lost</h2></div>"
    )
    st.html(
        f"""
        <article class="f1pi-explanation">
          <p>{escape(comparison.explanation.text)}</p>
          <div><span>Largest sector loss</span>
            <strong>{_sector_loss(comparison)}</strong></div>
          <div><span>Key corner</span>
            <strong>{escape(comparison.explanation.key_corner or "Unavailable")}</strong></div>
        </article>
        """
    )

    st.html('<div class="f1pi-result-section"><span>03</span><h2>Circuit trace</h2></div>')
    st.plotly_chart(
        track_figure(comparison), config=PLOT_CONFIG, width="stretch", key="track_map"
    )

    st.html('<div class="f1pi-result-section"><span>04</span><h2>Live delta</h2></div>')
    st.caption("Positive values mean Driver A is ahead; negative values mean Driver B is ahead.")
    st.plotly_chart(
        delta_figure(comparison), config=PLOT_CONFIG, width="stretch", key="live_delta"
    )

    st.html('<div class="f1pi-result-section"><span>05</span><h2>Speed</h2></div>')
    st.plotly_chart(
        speed_figure(comparison), config=PLOT_CONFIG, width="stretch", key="speed_trace"
    )

    st.html('<div class="f1pi-result-section"><span>06</span><h2>Driver inputs</h2></div>')
    if comparison.telemetry[["lap_a_brake", "lap_b_brake"]].isna().all().all():
        st.info("Brake channels are unavailable for both selected laps; throttle remains visible.")
    st.plotly_chart(
        inputs_figure(comparison), config=PLOT_CONFIG, width="stretch", key="driver_inputs"
    )

    st.html('<div class="f1pi-result-section"><span>07</span><h2>Corner losses</h2></div>')
    corner_figure = corner_loss_figure(comparison)
    if corner_figure is None:
        st.info("Corner-level evidence is unavailable for this session.")
    else:
        st.plotly_chart(
            corner_figure,
            config=PLOT_CONFIG,
            width="stretch",
            key="corner_losses",
        )


def _render_summary(session: LoadedSession, comparison: LapComparison) -> None:
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


def _sector_loss(comparison: LapComparison) -> str:
    sector = comparison.explanation.largest_loss_sector
    loss = comparison.explanation.sector_loss_seconds
    return "Unavailable" if sector is None else f"Sector {sector} · {format_delta(loss)}"
