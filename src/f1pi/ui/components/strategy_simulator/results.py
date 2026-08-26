"""Readable strategy-simulation result views."""

from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from f1pi.analysis.models import StrategyOutcomeSummary, StrategySimulationAnalysis
from f1pi.ui.components.results.chrome import render_result_section
from f1pi.ui.models import StrategySimulationRun
from f1pi.ui.strategy_charts import finish_distribution_figure, position_trace_figure
from f1pi.ui.strategy_formatting import (
    format_gap,
    format_position,
    format_probability,
    format_strategy_time,
    strategy_warning_message,
)

PLOT_CONFIG: dict[str, Any] = {
    "displayModeBar": False,
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": False,
}


def render_strategy_results(run: StrategySimulationRun) -> None:
    analysis = run.analysis
    _render_headline(analysis)
    _render_warnings(analysis)
    st.html(
        """
        <div class="f1pi-results-guide"><span>Read the counterfactual</span>
          <p>Compare candidate outcomes with the observed baseline, follow the projected race
          position, then inspect calibration support and the assumptions that bound the result.</p>
        </div>
        """
    )
    outcomes, traces, quality = st.tabs(
        [
            ":material/flag: Outcomes",
            ":material/timeline: Race trace",
            ":material/verified: Model & data",
        ]
    )
    with outcomes:
        _render_outcomes(analysis)
    with traces:
        _render_traces(analysis)
    with quality:
        _render_quality(analysis)


def _render_headline(analysis: StrategySimulationAnalysis) -> None:
    candidates = [summary for summary in analysis.summaries if summary.strategy != "baseline"]
    best = min(
        candidates,
        key=lambda item: (
            item.expected_delta_to_baseline_seconds,
            item.expected_finish_position,
        ),
    )
    st.html(
        f"""
        <section class="f1pi-strategy-result-hero" aria-labelledby="strategy-result-title">
          <div class="f1pi-result-hero__event">
            <span>{analysis.metadata.year} · {escape(analysis.metadata.session_name)} ·
              decision lap {analysis.decision_lap}</span>
            <h1 id="strategy-result-title">{escape(analysis.driver)} strategy range</h1>
            <p>{escape(analysis.metadata.event_name)} · {escape(analysis.metadata.location)}</p>
          </div>
          <div class="f1pi-strategy-headline-card"><span>Strongest mean time result</span>
            <strong>{escape(_label(best.strategy))}</strong>
            <p>{format_strategy_time(best.expected_delta_to_baseline_seconds)} vs baseline ·
              {format_probability(best.probability_better_than_baseline)} better</p>
            <small>Under the {escape(_label(best.scenario))} scenario</small></div>
        </section>
        """
    )


def _render_warnings(analysis: StrategySimulationAnalysis) -> None:
    if not analysis.warnings:
        return
    messages = "\n".join(
        f"- {strategy_warning_message(warning)}" for warning in analysis.warnings
    )
    st.warning(f"Simulation notes\n\n{messages}", icon=":material/info:")


def _render_outcomes(analysis: StrategySimulationAnalysis) -> None:
    scenarios = tuple(dict.fromkeys(summary.scenario for summary in analysis.summaries))
    for scenario_index, scenario in enumerate(scenarios, start=1):
        render_result_section(
            scenario_index,
            _label(scenario),
            "Expected values summarize all paired simulation runs; they are not "
            "single-race predictions.",
        )
        summaries = [summary for summary in analysis.summaries if summary.scenario == scenario]
        st.html(
            '<div class="f1pi-strategy-card-grid">'
            + "".join(_outcome_card(summary) for summary in summaries)
            + "</div>"
        )
        st.dataframe(
            _summary_frame(summaries),
            hide_index=True,
            width="stretch",
        )


def _render_traces(analysis: StrategySimulationAnalysis) -> None:
    scenarios = tuple(dict.fromkeys(summary.scenario for summary in analysis.summaries))
    scenario = st.selectbox(
        "Scenario shown",
        scenarios,
        format_func=_label,
        key="f1pi_strategy_result_scenario",
    )
    render_result_section(
        1,
        "Position through the remaining race",
        "Lines are median positions; shaded regions cover the configured confidence interval.",
    )
    st.plotly_chart(
        position_trace_figure(analysis, scenario),
        config=PLOT_CONFIG,
        width="stretch",
        key="strategy_position_trace",
    )
    render_result_section(
        2,
        "Finish distribution",
        "Bars show how often each finishing position occurred across the paired runs.",
    )
    st.plotly_chart(
        finish_distribution_figure(analysis, scenario),
        config=PLOT_CONFIG,
        width="stretch",
        key="strategy_finish_distribution",
    )


def _render_quality(analysis: StrategySimulationAnalysis) -> None:
    diagnostics = analysis.diagnostics
    render_result_section(
        1,
        "Calibration support",
        "These counts and errors show how much session evidence supports the simulator.",
    )
    st.html(
        f"""
        <div class="f1pi-strategy-diagnostic-grid">
          <article><span>Pace observations</span>
            <strong>{diagnostics.pace_observation_count:,}</strong>
            <small>{diagnostics.target_pace_observation_count:,} for
              {escape(analysis.driver)}</small></article>
          <article><span>Pit samples</span><strong>{diagnostics.pit_stop_sample_count:,}</strong>
            <small>session-specific stop losses</small></article>
          <article><span>Traffic samples</span><strong>{diagnostics.traffic_sample_count:,}</strong>
            <small>gap-dependent pace losses</small></article>
          <article><span>Pace error</span><strong>{diagnostics.pace_mae_seconds:.3f}s</strong>
            <small>MAE · RMSE {diagnostics.pace_rmse_seconds:.3f}s</small></article>
        </div>
        """
    )
    render_result_section(
        2,
        "Plans and boundaries",
        "The baseline is reconstructed from observed future stops; candidates replace only "
        "the target driver's future sequence.",
    )
    st.dataframe(_plan_frame(analysis), hide_index=True, width="stretch")
    st.info(
        "This is a retrospective, session-calibrated counterfactual. It does not optimize a "
        "strategy, enforce tire regulations, predict failures, or recreate individual overtakes.",
        icon=":material/info:",
    )


def _outcome_card(summary: StrategyOutcomeSummary) -> str:
    baseline = summary.strategy == "baseline"
    delta = "Observed-plan reference" if baseline else (
        f"{format_strategy_time(summary.expected_delta_to_baseline_seconds)} vs baseline"
    )
    better_than_baseline = (
        "Reference"
        if baseline
        else format_probability(summary.probability_better_than_baseline)
    )
    return f"""
      <article class="f1pi-strategy-card{' is-baseline' if baseline else ''}">
        <span>{escape(_label(summary.strategy))}</span>
        <strong>{format_position(summary.expected_finish_position)}</strong>
        <p>{escape(delta)}</p>
        <small>{format_probability(summary.podium_probability)} podium ·
          {better_than_baseline} better than baseline ·
          {format_gap(summary.expected_gap_to_winner_seconds)} to winner</small>
      </article>
    """


def _summary_frame(summaries: list[StrategyOutcomeSummary]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Plan": _label(item.strategy),
                "Expected finish": format_position(item.expected_finish_position),
                "Median finish": format_position(item.median_finish_position),
                "Win": format_probability(item.win_probability),
                "Podium": format_probability(item.podium_probability),
                "Top 10": format_probability(item.top_ten_probability),
                "Gap to winner": format_gap(item.expected_gap_to_winner_seconds),
                "Time vs baseline": (
                    "Reference"
                    if item.strategy == "baseline"
                    else format_strategy_time(item.expected_delta_to_baseline_seconds)
                ),
                "Better than baseline": (
                    "Reference"
                    if item.strategy == "baseline"
                    else format_probability(item.probability_better_than_baseline)
                ),
            }
            for item in summaries
        ]
    )


def _plan_frame(analysis: StrategySimulationAnalysis) -> pd.DataFrame:
    plans: dict[str, str] = {
        "Baseline": _stops_label(analysis.baseline.stops),
    }
    for summary in analysis.summaries:
        if summary.strategy != "baseline":
            plans.setdefault(_label(summary.strategy), "Candidate plan entered above")
    return pd.DataFrame([{"Plan": name, "Stops": stops} for name, stops in plans.items()])


def _stops_label(stops: tuple[Any, ...]) -> str:
    if not stops:
        return "No remaining stops"
    return " · ".join(
        f"after lap {stop.after_lap}: {stop.compound.title()} "
        f"(age {stop.starting_tire_age_laps:.1f})"
        for stop in stops
    )


def _label(value: str) -> str:
    return value.replace("_", " ").strip().title()
