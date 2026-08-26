"""Headings and contextual chrome for the strategy simulator."""

from __future__ import annotations

from html import escape

import streamlit as st

from f1pi.domain.models import ScheduledEvent, ScheduledSession
from f1pi.ui.models import StrategySimulationRun, StrategySimulationSetup


def render_strategy_intro() -> None:
    st.html(
        """
        <section class="f1pi-analysis-intro f1pi-strategy-intro" aria-labelledby="strategy-title">
          <div><p class="f1pi-eyebrow"><span></span> Race strategy intelligence</p>
            <h1 id="strategy-title">Test the call before rewriting the race.</h1></div>
          <p>Compare explicit future pit plans from a chosen decision lap. Every outcome is a
          hindsight-calibrated range—not a claim that the simulator can predict a future race.</p>
        </section>
        """
    )


def render_strategy_session_context(event: ScheduledEvent, session: ScheduledSession) -> None:
    st.html(
        f"""
        <aside class="f1pi-session-context" aria-label="Selected strategy session">
          <div><span>Selected race</span>
            <strong>{escape(event.event_name)} · {escape(session.name)}</strong>
            <small>Round {event.round_number} · {escape(event.location)} ·
              {session.starts_at_utc:%d %b %Y, %H:%M UTC}</small></div>
          <p><b>What is compared</b> The observed remaining strategy and your candidate stop
          plans, simulated against the full classified field with paired random samples.</p>
        </aside>
        """
    )


def render_setup_ready(setup: StrategySimulationSetup) -> None:
    source = "Local snapshot reused" if setup.snapshot_reused else "New snapshot prepared"
    st.html(
        f"""
        <aside class="f1pi-tire-ready" aria-label="Loaded strategy race">
          <span class="f1pi-session-ready__icon" aria-hidden="true">✓</span>
          <div><span>Race ready</span><strong>{escape(setup.metadata.event_name)} ·
            {escape(setup.metadata.session_name)}</strong>
            <small>{setup.race_laps} laps · {len(setup.drivers)} classified drivers ·
              {len(setup.compounds)} observed compounds</small></div>
          <span class="f1pi-session-ready__source">{escape(source)}</span>
        </aside>
        """
    )


def render_simulation_ready(run: StrategySimulationRun) -> None:
    analysis = run.analysis
    scenarios = len({summary.scenario for summary in analysis.summaries})
    strategies = len({summary.strategy for summary in analysis.summaries})
    iterations = int(analysis.outcome_samples["iteration"].nunique())
    st.html(
        f"""
        <aside class="f1pi-strategy-ready" aria-label="Current strategy simulation">
          <span class="f1pi-session-ready__icon" aria-hidden="true">✓</span>
          <div><span>Simulation ready</span>
            <strong>{escape(analysis.driver)} · decision after lap {analysis.decision_lap}</strong>
            <small>{strategies} plans · {scenarios} scenarios ·
              {iterations:,} paired runs each</small>
          </div><span class="f1pi-session-ready__source">Hindsight calibrated</span>
        </aside>
        """
    )
