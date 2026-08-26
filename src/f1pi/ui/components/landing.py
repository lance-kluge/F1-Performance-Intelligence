"""Presentational sections for the product landing page."""

from __future__ import annotations

import streamlit as st


def render_hero_copy() -> None:
    st.html(
        """
        <section class="f1pi-hero-copy" aria-labelledby="hero-title">
          <p class="f1pi-eyebrow"><span></span> Telemetry, translated</p>
          <h1 id="hero-title">See where the lap was won.</h1>
          <p class="f1pi-hero-copy__lede">
            Compare two laps, follow the delta around the circuit, and turn raw telemetry into
            a clear account of where performance changed.
          </p>
          <div class="f1pi-proof-row" aria-label="Product capabilities">
            <span>Spatially aligned</span><span>Corner-level evidence</span><span>Local-first</span>
          </div>
        </section>
        """
    )


def render_analysis_preview() -> None:
    st.html(
        """
        <section class="f1pi-preview" aria-label="Illustrative lap comparison preview">
          <div class="f1pi-preview__topline">
            <span class="f1pi-label">Interface preview · illustrative data</span>
            <span class="f1pi-live-dot">Analysis ready</span>
          </div>
          <div class="f1pi-preview__event">
            <div><span class="f1pi-kicker">2026 · Qualifying</span>
              <h2>Australian Grand Prix</h2></div>
            <span class="f1pi-preview__lap">Fastest laps</span>
          </div>
          <div class="f1pi-driver-grid">
            <article class="f1pi-driver-card f1pi-driver-card--a">
              <span class="f1pi-driver-card__tag">Driver A</span>
              <strong>NOR</strong><small>Reference · 1:15.096</small>
            </article>
            <article class="f1pi-driver-card f1pi-driver-card--b">
              <span class="f1pi-driver-card__tag">Driver B</span>
              <strong>VER</strong><small>+0.184 seconds</small>
            </article>
          </div>
          <div class="f1pi-sector-grid" aria-label="Illustrative sector deltas">
            <div><span>S1</span><i style="--bar:32%"></i><strong>+0.041</strong></div>
            <div><span>S2</span><i class="is-gain" style="--bar:18%"></i>
              <strong>-0.022</strong></div>
            <div><span>S3</span><i style="--bar:78%"></i><strong>+0.165</strong></div>
          </div>
          <div class="f1pi-loss-callout">
            <span class="f1pi-label">Largest observed loss</span>
            <strong>Turn 3 <em>+0.083s</em></strong>
            <span>Lower minimum speed, with throttle applied later on exit.</span>
          </div>
          <div class="f1pi-trace" aria-hidden="true">
            <svg viewBox="0 0 680 92" preserveAspectRatio="none">
              <path class="grid" d="M0 23H680M0 46H680M0 69H680"/>
              <path class="zero" d="M0 48H680"/>
              <path class="delta"
                d="M0 48 C70 45,85 34,140 40 S230 63,286 50 S370 25,430 37
                S530 74,680 27"/>
            </svg>
          </div>
        </section>
        """
    )


def render_benefits() -> None:
    st.html(
        """
        <section class="f1pi-section" aria-labelledby="benefits-title">
          <p class="f1pi-eyebrow"><span></span> Performance intelligence</p>
          <h2 id="benefits-title">From timing screen to track-level understanding.</h2>
          <div class="f1pi-card-grid">
            <article class="f1pi-feature-card"><b>01</b><h3>Compare</h3>
              <p>Place two accurate laps on one spatial axis so every sample describes the same
              point on the circuit.</p></article>
            <article class="f1pi-feature-card"><b>02</b><h3>Locate</h3>
              <p>Trace the live delta through sectors and corners to see precisely where the gap
              opened or closed.</p></article>
            <article class="f1pi-feature-card"><b>03</b><h3>Understand</h3>
              <p>Connect time loss to measured speed, throttle, and braking evidence without
              inventing a causal story.</p></article>
          </div>
        </section>
        """
    )


def render_analysis_choice_intro() -> None:
    st.html(
        """
        <section class="f1pi-analysis-choice-intro" aria-labelledby="analysis-choice-title">
          <p class="f1pi-eyebrow"><span></span> Analysis workspaces</p>
          <h2 id="analysis-choice-title">Start with the performance question.</h2>
          <p>Compare two laps at the same points on track, or model how lap time changes as each
          compound ages through a race stint.</p>
        </section>
        """
    )


def render_lap_analysis_choice() -> None:
    st.html(
        """
        <article class="f1pi-analysis-choice">
          <span>01 · Lap analysis</span>
          <h3>Where did the lap time move?</h3>
          <p>Align two accurate laps by distance, trace the delta, and inspect speed, inputs,
          sectors, and corners.</p>
          <small>Best for qualifying and driver-to-driver comparisons</small>
        </article>
        """
    )


def render_tire_degradation_choice() -> None:
    st.html(
        """
        <article class="f1pi-analysis-choice f1pi-analysis-choice--tire">
          <span>02 · Tire degradation</span>
          <h3>How did each compound evolve?</h3>
          <p>Reconstruct clean race stints, estimate compound-specific lap-time trends, and audit
          uncertainty, validation, and every included lap.</p>
          <small>Best for completed Races and Sprints</small>
        </article>
        """
    )


def render_strategy_simulator_choice() -> None:
    st.html(
        """
        <article class="f1pi-analysis-choice f1pi-analysis-choice--strategy">
          <span>03 · Strategy simulator</span>
          <h3>What if we stopped on another lap?</h3>
          <p>Set a decision point, compare explicit future pit plans, and inspect outcome ranges
          under observed or green-race conditions.</p>
          <small>Best for retrospective Race and Sprint counterfactuals</small>
        </article>
        """
    )


def render_workflow() -> None:
    st.html(
        """
        <section class="f1pi-section f1pi-workflow" aria-labelledby="workflow-title">
          <div><p class="f1pi-eyebrow"><span></span> A focused workflow</p>
            <h2 id="workflow-title">Three choices. One readable comparison.</h2></div>
          <ol>
            <li><b>01</b><div><strong>Select a session</strong><span>Season, race weekend,
              and session type.</span></div></li>
            <li><b>02</b><div><strong>Choose two laps</strong><span>Fastest accurate laps or
              exact lap numbers.</span></div></li>
            <li><b>03</b><div><strong>Inspect the evidence</strong><span>Delta, speed, inputs,
              sectors, corners, and explanation.</span></div></li>
          </ol>
        </section>
        """
    )


def render_methodology() -> None:
    st.html(
        """
        <section class="f1pi-method" aria-labelledby="method-title">
          <div class="f1pi-method__graphic" aria-hidden="true">
            <svg viewBox="0 0 380 310">
              <path class="track-shadow"
                d="M95 261C32 208 54 136 103 115c51-22 32-73 87-88 55-16 98 19
                102 66 4 40 48 61 37 111-13 61-80 82-129 45-35-26-70 38-105 12Z"/>
              <path class="track"
                d="M95 261C32 208 54 136 103 115c51-22 32-73 87-88 55-16 98 19
                102 66 4 40 48 61 37 111-13 61-80 82-129 45-35-26-70 38-105 12Z"/>
              <circle cx="102" cy="116" r="6"/><circle cx="292" cy="94" r="6"/>
              <circle cx="201" cy="249" r="6"/>
            </svg>
          </div>
          <div class="f1pi-method__copy">
            <p class="f1pi-eyebrow"><span></span> Method over mythology</p>
            <h2 id="method-title">The comparison respects the circuit.</h2>
            <p>Laps are synchronized by distance rather than elapsed time, keeping two drivers
            aligned to the same physical location even after a gap develops.</p>
            <ul><li>Accurate timed laps by default</li><li>Signed sector and live deltas</li>
              <li>Claims limited to observable telemetry</li></ul>
          </div>
        </section>
        """
    )


def render_final_callout() -> None:
    st.html(
        """
        <section class="f1pi-final-callout" aria-labelledby="final-title">
          <p class="f1pi-label">Performance intelligence</p>
          <h2 id="final-title">Read the lap. Understand the stint.</h2>
          <p>Use measured telemetry and explicit model boundaries to answer the question at
          hand.</p>
        </section>
        """
    )
