"""Plotly figure factories for strategy counterfactuals."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from f1pi.analysis.models import StrategySimulationAnalysis

TEXT_COLOR = "#f5f3ed"
MUTED_COLOR = "#aaa7a0"
GRID_COLOR = "rgba(245, 243, 237, 0.10)"
TRANSPARENT = "rgba(0,0,0,0)"
STRATEGY_COLORS = ("#f5f3ed", "#ff4f47", "#67d2a0", "#f1c84b", "#5f8cff")


def position_trace_figure(
    analysis: StrategySimulationAnalysis, scenario: str
) -> go.Figure:
    """Show target median position and its confidence interval by simulated lap."""
    target = analysis.lap_distributions.loc[
        analysis.lap_distributions["scenario"].eq(scenario)
        & analysis.lap_distributions["driver"].eq(analysis.driver)
    ]
    figure = go.Figure()
    for index, (strategy, rows) in enumerate(target.groupby("strategy", sort=False)):
        rows = rows.sort_values("lap_number")
        color = STRATEGY_COLORS[index % len(STRATEGY_COLORS)]
        _add_interval(figure, rows, str(strategy), color)
    figure.update_layout(
        title={"text": "Projected track position", "x": 0},
        xaxis_title="Race lap",
        yaxis_title="Position",
        height=470,
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=TRANSPARENT,
        font={"color": TEXT_COLOR, "family": "Inter, sans-serif", "size": 12},
        hovermode="x unified",
        margin={"l": 55, "r": 24, "t": 65, "b": 52},
        legend={"orientation": "h", "y": 1.12, "x": 0},
    )
    figure.update_xaxes(gridcolor=GRID_COLOR, zeroline=False, tickformat=".0f")
    figure.update_yaxes(
        gridcolor=GRID_COLOR,
        zeroline=False,
        autorange="reversed",
        tickformat=".0f",
        dtick=1,
    )
    return figure


def finish_distribution_figure(
    analysis: StrategySimulationAnalysis, scenario: str
) -> go.Figure:
    """Compare empirical finish-position probabilities for every strategy."""
    samples = analysis.outcome_samples.loc[analysis.outcome_samples["scenario"].eq(scenario)]
    figure = go.Figure()
    for index, (strategy, rows) in enumerate(samples.groupby("strategy", sort=False)):
        probabilities = (
            rows["finish_position"].value_counts(normalize=True).sort_index().mul(100)
        )
        figure.add_trace(
            go.Bar(
                x=probabilities.index,
                y=probabilities.values,
                name=str(strategy).replace("_", " ").title(),
                marker_color=STRATEGY_COLORS[index % len(STRATEGY_COLORS)],
                opacity=0.82,
                hovertemplate="Finish P%{x:.0f}<br>%{y:.1f}% of runs<extra></extra>",
            )
        )
    figure.update_layout(
        title={"text": "Finish-position distribution", "x": 0},
        barmode="group",
        xaxis_title="Finish position",
        yaxis_title="Probability",
        height=390,
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=TRANSPARENT,
        font={"color": TEXT_COLOR, "family": "Inter, sans-serif", "size": 12},
        margin={"l": 55, "r": 24, "t": 65, "b": 52},
        legend={"orientation": "h", "y": 1.14, "x": 0},
    )
    figure.update_xaxes(gridcolor=GRID_COLOR, zeroline=False, tickformat=".0f", dtick=1)
    figure.update_yaxes(gridcolor=GRID_COLOR, zeroline=False, ticksuffix="%", tickformat=".0f")
    return figure


def _add_interval(
    figure: go.Figure, rows: pd.DataFrame, strategy: str, color: str
) -> None:
    label = strategy.replace("_", " ").title()
    x_values = rows["lap_number"].tolist()
    figure.add_trace(
        go.Scatter(
            x=x_values + x_values[::-1],
            y=rows["position_upper"].tolist() + rows["position_lower"].tolist()[::-1],
            fill="toself",
            fillcolor=_with_alpha(color, 0.09),
            line={"color": TRANSPARENT},
            hoverinfo="skip",
            showlegend=False,
            legendgroup=strategy,
        )
    )
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=rows["position_median"],
            mode="lines",
            name=label,
            legendgroup=strategy,
            line={
                "color": color,
                "width": 2.5,
                "dash": "dot" if strategy == "baseline" else "solid",
            },
            customdata=rows[["position_lower", "position_upper"]],
            hovertemplate=(
                f"{label}<br>Lap %{{x:.0f}}<br>Median P%{{y:.1f}}<br>"
                "Interval P%{customdata[0]:.1f}-P%{customdata[1]:.1f}<extra></extra>"
            ),
        )
    )


def _with_alpha(color: str, alpha: float) -> str:
    red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
    return f"rgba({red},{green},{blue},{alpha})"
