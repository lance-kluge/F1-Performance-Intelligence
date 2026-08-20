"""Workspace headings and progress navigation."""

from __future__ import annotations

from html import escape

import streamlit as st


def render_workspace_intro() -> None:
    """Introduce the task without pushing its controls below the fold."""
    st.html(
        """
        <section class="f1pi-analysis-intro" aria-labelledby="analysis-title">
          <div>
            <p class="f1pi-eyebrow"><span></span> Interactive workspace</p>
            <h1 id="analysis-title">Compare the lap, not just the time.</h1>
          </div>
          <p>Select a completed session, choose two accurate laps, and see where performance
          changed around the circuit. Your FastF1 data and snapshots stay on this machine.</p>
        </section>
        """
    )


def render_workflow_progress(active_step: int) -> None:
    """Show users where they are in the three-step comparison workflow."""
    steps = (
        (1, "Session", "Choose and load telemetry"),
        (2, "Laps", "Pick two accurate laps"),
        (3, "Analysis", "Read the evidence"),
    )
    items = []
    for number, title, detail in steps:
        if number < active_step:
            state, state_label = "complete", "Complete"
        elif number == active_step:
            state, state_label = "active", "Current"
        else:
            state, state_label = "next", "Next"
        items.append(
            f"""
            <li class="f1pi-progress__item f1pi-progress__item--{state}">
              <span class="f1pi-progress__number">{number:02d}</span>
              <span class="f1pi-progress__copy"><strong>{escape(title)}</strong>
                <small>{escape(detail)}</small></span>
              <span class="f1pi-progress__state">{state_label}</span>
            </li>
            """
        )
    st.html(
        '<nav class="f1pi-progress" aria-label="Analysis progress"><ol>'
        + "".join(items)
        + "</ol></nav>"
    )


def render_step_header(number: int, title: str, detail: str) -> None:
    """Render a consistent section marker for one workflow step."""
    st.html(
        f"""
        <header class="f1pi-stage">
          <span>{number:02d}</span>
          <div><h2>{escape(title)}</h2><p>{escape(detail)}</p></div>
        </header>
        """
    )
