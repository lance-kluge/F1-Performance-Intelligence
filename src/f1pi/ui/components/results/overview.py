"""Outcome, location, and track-level result view."""

from __future__ import annotations

from collections.abc import Mapping
from html import escape

import streamlit as st

from f1pi.analysis.models import LapComparison
from f1pi.ui.charts import dominance_shares, sector_figure, track_figure
from f1pi.ui.components.results.chrome import render_result_section
from f1pi.ui.formatting import format_delta


def render_overview(comparison: LapComparison, plot_config: Mapping[str, object]) -> None:
    """Render the comparison story from sector result to physical location."""
    render_result_section(1, "Sector comparison", "See which driver gained in each timing sector.")
    st.plotly_chart(
        sector_figure(comparison),
        config=dict(plot_config),
        width="stretch",
        key="sector_comparison",
    )

    render_result_section(
        2, "Where the time was lost", "A measured summary of the largest differences."
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

    render_result_section(
        3, "Track dominance", "Locate where each driver gained around the circuit."
    )
    _render_dominance_summary(comparison)
    st.caption(
        "Line color shows who gained time locally across each 3% lap window. "
        "Grey sections were within 0.001 seconds. Hover over the track for the driver "
        "and local gain, plus the whole section gain when available. These are not "
        "the cumulative lap gap."
    )
    st.plotly_chart(
        track_figure(comparison),
        config=dict(plot_config),
        width="stretch",
        key="track_dominance",
    )


def _render_dominance_summary(comparison: LapComparison) -> None:
    lap_a_share, lap_b_share, neutral_share = dominance_shares(comparison)
    st.html(
        f"""
        <section class="f1pi-dominance-summary" aria-label="Track dominance summary">
          <article class="f1pi-dominance-summary__a">
            <span>{escape(comparison.lap_a.driver)} gained time</span>
            <strong>{lap_a_share:.1f}%</strong><small>of lap progress</small>
          </article>
          <article class="f1pi-dominance-summary__b">
            <span>{escape(comparison.lap_b.driver)} gained time</span>
            <strong>{lap_b_share:.1f}%</strong><small>of lap progress</small>
          </article>
          <article>
            <span>Within 0.001s</span>
            <strong>{neutral_share:.1f}%</strong><small>of lap progress</small>
          </article>
        </section>
        """
    )


def _sector_loss(comparison: LapComparison) -> str:
    sector = comparison.explanation.largest_loss_sector
    loss = comparison.explanation.sector_loss_seconds
    return "Unavailable" if sector is None else f"Sector {sector} · {format_delta(loss)}"
