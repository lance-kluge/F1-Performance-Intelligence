"""Readable tire-degradation result views."""

from __future__ import annotations

from dataclasses import asdict
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from f1pi.analysis.models import DegradationMode, TireDegradationAnalysis, TireModelMetrics
from f1pi.ui.components.results.chrome import render_result_section
from f1pi.ui.models import TireAnalysisRun
from f1pi.ui.tire_charts import (
    degradation_curve_figure,
    degradation_rate_figure,
    validation_figure,
)
from f1pi.ui.tire_formatting import (
    estimate_signal,
    exclusion_label,
    format_degradation_rate,
    warning_message,
)

PLOT_CONFIG = {
    "displayModeBar": False,
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": False,
}


def render_tire_results(run: TireAnalysisRun) -> None:
    """Render a headline summary and three progressively detailed result tabs."""
    analysis = run.analysis
    _render_summary(analysis)
    _render_warnings(analysis)
    st.html(
        """
        <div class="f1pi-results-guide">
          <span>Explore the model</span>
          <p>Start with compound trends, check out-of-sample accuracy, then inspect exactly
          which laps and stints entered the model.</p>
        </div>
        """
    )
    degradation, quality, audit = st.tabs(
        [
            ":material/trending_up: Degradation",
            ":material/verified: Model quality",
            ":material/fact_check: Data audit",
        ]
    )
    with degradation:
        _render_degradation(analysis)
    with quality:
        _render_quality(analysis)
    with audit:
        _render_audit(analysis)


def _render_summary(analysis: TireDegradationAnalysis) -> None:
    mode_label = "Condition-adjusted" if analysis.mode is DegradationMode.ADJUSTED else "Raw trend"
    modeled_count = int(analysis.observations["fitted_lap_time_seconds"].notna().sum())
    total_count = len(analysis.observations)
    st.html(
        f"""
        <section class="f1pi-tire-result-hero" aria-labelledby="tire-result-title">
          <div class="f1pi-result-hero__event">
            <span>{analysis.metadata.year} · {escape(analysis.metadata.session_name)}</span>
            <h1 id="tire-result-title">{escape(analysis.metadata.event_name)}</h1>
            <p>{escape(analysis.metadata.location)} · {escape(analysis.metadata.country)}</p>
          </div>
          <div class="f1pi-tire-stat-grid">
            <article><span>Model</span><strong>{escape(mode_label)}</strong>
              <small>95% confidence intervals</small></article>
            <article><span>Modeled laps</span><strong>{modeled_count}</strong>
              <small>of {total_count} observed laps</small></article>
            <article><span>Stints</span><strong>{len(analysis.stints)}</strong>
              <small>stable tire runs audited</small></article>
            <article><span>Compounds</span><strong>{len(analysis.estimates)}</strong>
              <small>met support thresholds</small></article>
          </div>
        </section>
        """
    )


def _render_warnings(analysis: TireDegradationAnalysis) -> None:
    if not analysis.warnings:
        return
    messages = "\n".join(f"- {warning_message(warning)}" for warning in analysis.warnings)
    st.warning(f"Model notes\n\n{messages}", icon=":material/info:")


def _render_degradation(analysis: TireDegradationAnalysis) -> None:
    render_result_section(
        1,
        "Compound trends",
        "Positive values mean lap time increased as the tire aged; bars show 95% intervals.",
    )
    st.html(
        '<div class="f1pi-compound-grid">'
        + "".join(_estimate_card(estimate) for estimate in analysis.estimates)
        + "</div>"
    )
    st.plotly_chart(
        degradation_rate_figure(analysis),
        config=PLOT_CONFIG,
        width="stretch",
        key="tire_degradation_rates",
    )
    render_result_section(
        2,
        "Modeled stint shape",
        "Lines stay inside each compound's observed tire-age range; shaded areas show uncertainty.",
    )
    st.plotly_chart(
        degradation_curve_figure(analysis),
        config=PLOT_CONFIG,
        width="stretch",
        key="tire_degradation_curves",
    )
    st.caption(
        "Dots are clean laps. Dark bands show confidence in the modeled mean; lighter outer "
        "bands show the wider range expected for an individual lap."
    )


def _estimate_card(estimate: Any) -> str:
    compound_class = "".join(
        character for character in estimate.compound.lower() if character.isalnum()
    )
    interval = (
        f"{estimate.confidence_lower_seconds_per_lap:+.3f} to "
        f"{estimate.confidence_upper_seconds_per_lap:+.3f} s/lap"
    )
    return f"""
      <article class="f1pi-compound-card f1pi-compound-card--{compound_class}">
        <span>{escape(estimate.compound.title())}</span>
        <strong>{format_degradation_rate(estimate.seconds_per_lap)}</strong>
        <p>{escape(estimate_signal(estimate))}</p>
        <small>95% interval {escape(interval)} · {estimate.observation_count} laps ·
          {estimate.stint_count} stints · age
          {estimate.minimum_tire_age:g}&ndash;{estimate.maximum_tire_age:g}</small>
      </article>
    """


def _render_quality(analysis: TireDegradationAnalysis) -> None:
    metrics = analysis.validation.overall
    render_result_section(
        1,
        "Out-of-sample accuracy",
        "Whole stints are held out, so laps from one physical stint never train and test together.",
    )
    st.html(_metric_cards(metrics, analysis.validation.fold_count))
    st.plotly_chart(
        validation_figure(analysis),
        config=PLOT_CONFIG,
        width="stretch",
        key="tire_validation_error",
    )
    improvement = metrics.baseline_mae_seconds - metrics.mae_seconds
    if improvement > 0:
        st.info(
            f"The model improves mean absolute error by {improvement:.3f}s versus a simple "
            "compound-average baseline on the scored laps.",
            icon=":material/check_circle:",
        )
    else:
        st.info(
            "The model does not beat the simple compound-average baseline in this session. "
            "Treat the fitted slopes as descriptive rather than strongly predictive.",
            icon=":material/info:",
        )
    render_result_section(
        2,
        "Interpretation boundary",
        "What this single-session model can and cannot support.",
    )
    st.html(
        """
        <div class="f1pi-model-boundary">
          <article><span>Supported</span><p>Conditional associations between tire age and lap
          time within this session, with measured conditions controlled where
          possible.</p></article>
          <article><span>Not established</span><p>Causal tire performance independent of traffic,
          energy deployment, damage, setup, driver intent, fuel, or track evolution.</p></article>
        </div>
        """
    )


def _metric_cards(metrics: TireModelMetrics, folds: int) -> str:
    r_squared = "Unavailable" if metrics.r_squared is None else f"{metrics.r_squared:.2f}"
    return f"""
      <div class="f1pi-quality-grid">
        <article><span>Model MAE</span><strong>{metrics.mae_seconds:.3f}s</strong>
          <small>mean absolute error</small></article>
        <article><span>Model RMSE</span><strong>{metrics.rmse_seconds:.3f}s</strong>
          <small>penalizes larger misses</small></article>
        <article><span>R²</span><strong>{r_squared}</strong>
          <small>held-out variance explained</small></article>
        <article><span>Validation</span><strong>{folds} folds</strong>
          <small>{metrics.observation_count} laps scored</small></article>
      </div>
    """


def _render_audit(analysis: TireDegradationAnalysis) -> None:
    render_result_section(
        1,
        "Lap eligibility",
        "Every observed lap is retained with one deterministic inclusion or exclusion decision.",
    )
    st.dataframe(
        _eligibility_summary(analysis.observations),
        hide_index=True,
        width="stretch",
        column_config={
            "Decision": st.column_config.TextColumn("Decision"),
            "Laps": st.column_config.NumberColumn("Laps", format="%d"),
            "Share": st.column_config.ProgressColumn("Share", min_value=0.0, max_value=1.0),
        },
    )
    render_result_section(
        2,
        "Stable stints",
        "Stints split when the compound changes, a lap is skipped, or reported tire age resets.",
    )
    st.dataframe(
        _stint_frame(analysis),
        hide_index=True,
        width="stretch",
        column_config={
            "Clean laps": st.column_config.NumberColumn(format="%d"),
            "Excluded laps": st.column_config.NumberColumn(format="%d"),
        },
    )
    with st.expander("Inspect lap-level model data"):
        st.caption(
            "Fitted values and residuals appear only for laps used by a supported compound model."
        )
        st.dataframe(
            _observation_frame(analysis.observations),
            hide_index=True,
            width="stretch",
        )


def _eligibility_summary(observations: pd.DataFrame) -> pd.DataFrame:
    decisions = observations["exclusion_reason"].fillna("").astype(str)
    decisions = decisions.mask(decisions.eq(""), "included")
    below_support = observations["eligible"] & observations["fitted_lap_time_seconds"].isna()
    decisions = decisions.mask(below_support, "below_compound_support")
    counts = decisions.value_counts()
    total = max(len(observations), 1)
    return pd.DataFrame(
        {
            "Decision": [_decision_label(reason) for reason in counts.index],
            "Laps": counts.to_numpy(dtype=int),
            "Share": counts.to_numpy(dtype=float) / total,
        }
    )


def _decision_label(reason: str) -> str:
    if reason == "included":
        return "Included in model"
    if reason == "below_compound_support":
        return "Compound below support threshold"
    return exclusion_label(reason)


def _stint_frame(analysis: TireDegradationAnalysis) -> pd.DataFrame:
    rows = []
    for stint in analysis.stints:
        row = asdict(stint)
        rows.append(
            {
                "Driver": row["driver"],
                "Compound": str(row["compound"]).title(),
                "Race laps": f"{row['start_lap']}-{row['end_lap']}",
                "Tire age": f"{row['start_tire_age']:g}-{row['end_tire_age']:g}",
                "Clean laps": row["included_laps"],
                "Excluded laps": row["excluded_laps"],
                "Set": _fresh_tire_label(row["fresh_tyre"]),
            }
        )
    return pd.DataFrame(rows)


def _observation_frame(observations: pd.DataFrame) -> pd.DataFrame:
    display = observations.loc[
        :,
        [
            "driver",
            "lap_number",
            "compound",
            "tire_age_laps",
            "lap_time_seconds",
            "eligible",
            "exclusion_reason",
            "fitted_lap_time_seconds",
            "residual_seconds",
        ],
    ].copy()
    display["compound"] = display["compound"].astype(str).str.title()
    display["exclusion_reason"] = (
        display["exclusion_reason"]
        .fillna("")
        .map(lambda reason: "—" if not reason else exclusion_label(str(reason)))
    )
    display.columns = [
        "Driver",
        "Lap",
        "Compound",
        "Tire age",
        "Lap time (s)",
        "Included",
        "Decision",
        "Fitted time (s)",
        "Residual (s)",
    ]
    return display


def _fresh_tire_label(value: bool | None) -> str:
    if value is True:
        return "New"
    if value is False:
        return "Used"
    return "Unknown"
