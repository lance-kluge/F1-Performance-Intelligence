"""Pure Plotly figure factories for tire-degradation analysis."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from f1pi.analysis.models import TireDegradationAnalysis

PANEL_COLOR = "#141417"
TEXT_COLOR = "#f5f3ed"
MUTED_COLOR = "#aaa7a0"
GRID_COLOR = "rgba(245, 243, 237, 0.10)"
TRANSPARENT = "rgba(0,0,0,0)"
COMPOUND_COLORS = {
    "SOFT": "#ff4f47",
    "MEDIUM": "#f1c84b",
    "HARD": "#f5f3ed",
    "INTERMEDIATE": "#67d2a0",
    "WET": "#5f8cff",
}
FALLBACK_COLORS = ("#b47cff", "#ff9e64", "#56c7d9", "#d789b9")


def degradation_rate_figure(analysis: TireDegradationAnalysis) -> go.Figure:
    """Show compound slopes and their coefficient confidence intervals."""
    estimates = analysis.estimates
    figure = go.Figure(
        go.Scatter(
            x=[estimate.seconds_per_lap for estimate in estimates],
            y=[estimate.compound.title() for estimate in estimates],
            mode="markers",
            marker={
                "color": [compound_color(estimate.compound) for estimate in estimates],
                "size": 12,
                "line": {"color": PANEL_COLOR, "width": 1},
            },
            error_x={
                "type": "data",
                "symmetric": False,
                "array": [
                    estimate.confidence_upper_seconds_per_lap - estimate.seconds_per_lap
                    for estimate in estimates
                ],
                "arrayminus": [
                    estimate.seconds_per_lap - estimate.confidence_lower_seconds_per_lap
                    for estimate in estimates
                ],
                "color": MUTED_COLOR,
                "thickness": 1.5,
                "width": 5,
            },
            customdata=[
                [
                    estimate.confidence_lower_seconds_per_lap,
                    estimate.confidence_upper_seconds_per_lap,
                    estimate.observation_count,
                    estimate.stint_count,
                ]
                for estimate in estimates
            ],
            hovertemplate=(
                "%{y}<br>%{x:+.3f} s/lap<br>"
                "95% interval %{customdata[0]:+.3f} to %{customdata[1]:+.3f}<br>"
                "%{customdata[2]} laps · %{customdata[3]} stints<extra></extra>"
            ),
            showlegend=False,
        )
    )
    figure.add_vline(x=0, line_color="rgba(245,243,237,.35)", line_width=1)
    return _base_figure(
        figure,
        title="Compound degradation rate",
        x_title="Lap-time change per tire lap (seconds)",
        height=max(260, 90 + 62 * len(estimates)),
        x_tickformat="+.3f",
    )


def degradation_curve_figure(analysis: TireDegradationAnalysis) -> go.Figure:
    """Overlay eligible laps, adjusted curves, and both uncertainty bands."""
    figure = go.Figure()
    eligible = analysis.observations.loc[analysis.observations["eligible"]]
    for estimate in analysis.estimates:
        compound = estimate.compound
        color = compound_color(compound)
        curve = analysis.curves.loc[analysis.curves["compound"].eq(compound)].sort_values(
            "tire_age_laps"
        )
        observations = eligible.loc[eligible["compound"].eq(compound)]
        _add_band(
            figure,
            curve,
            lower="prediction_lower_seconds",
            upper="prediction_upper_seconds",
            color=_with_alpha(color, 0.07),
            name=f"{compound.title()} prediction range",
            legendgroup=compound,
        )
        _add_band(
            figure,
            curve,
            lower="mean_confidence_lower_seconds",
            upper="mean_confidence_upper_seconds",
            color=_with_alpha(color, 0.16),
            name=f"{compound.title()} mean confidence",
            legendgroup=compound,
        )
        figure.add_trace(
            go.Scatter(
                x=curve["tire_age_laps"],
                y=curve["predicted_lap_time_seconds"],
                mode="lines",
                name=f"{compound.title()} reference-condition trend",
                legendgroup=compound,
                line={"color": color, "width": 2.5},
                hovertemplate=(
                    f"{compound.title()}<br>Tire age %{{x:.1f}} laps<br>"
                    "Modeled lap %{y:.3f}s<extra></extra>"
                ),
            )
        )
        figure.add_trace(
            go.Scatter(
                x=observations["tire_age_laps"],
                y=observations["lap_time_seconds"],
                mode="markers",
                name=f"{compound.title()} raw clean laps",
                legendgroup=compound,
                showlegend=False,
                marker={"color": color, "size": 5, "opacity": 0.34},
                customdata=observations[["driver", "lap_number", "stint_id"]],
                hovertemplate=(
                    f"{compound.title()}<br>%{{customdata[0]}} · lap %{{customdata[1]}}<br>"
                    "Tire age %{x:.1f} · raw lap time %{y:.3f}s<br>"
                    "Stint %{customdata[2]}<extra></extra>"
                ),
            )
        )
    return _base_figure(
        figure,
        title="Raw laps and reference-condition trend",
        x_title="Tire age (laps)",
        y_title="Lap time (seconds)",
        height=520,
        x_tickformat=".0f",
        y_tickformat=".1f",
    )


def validation_figure(analysis: TireDegradationAnalysis) -> go.Figure:
    """Compare out-of-fold model MAE with the simple compound-mean baseline."""
    metrics = (analysis.validation.overall, *analysis.validation.per_compound)
    labels = ["Overall" if item.scope == "overall" else item.scope.title() for item in metrics]
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=labels,
            y=[item.mae_seconds for item in metrics],
            name="Tire model",
            marker_color="#ff4f47",
            hovertemplate="%{x}<br>Model MAE %{y:.3f}s<extra></extra>",
        )
    )
    figure.add_trace(
        go.Bar(
            x=labels,
            y=[item.baseline_mae_seconds for item in metrics],
            name="Compound-mean baseline",
            marker_color="#6f6f74",
            hovertemplate="%{x}<br>Baseline MAE %{y:.3f}s<extra></extra>",
        )
    )
    figure.update_layout(barmode="group")
    return _base_figure(
        figure,
        title="Out-of-sample error",
        x_title=None,
        y_title="Mean absolute error (seconds)",
        height=360,
        y_tickformat=".2f",
    )


def _add_band(
    figure: go.Figure,
    curve: pd.DataFrame,
    *,
    lower: str,
    upper: str,
    color: str,
    name: str,
    legendgroup: str,
) -> None:
    x_values = curve["tire_age_laps"].tolist()
    figure.add_trace(
        go.Scatter(
            x=x_values + x_values[::-1],
            y=curve[upper].tolist() + curve[lower].tolist()[::-1],
            fill="toself",
            fillcolor=color,
            line={"color": "rgba(0,0,0,0)"},
            hoverinfo="skip",
            name=name,
            legendgroup=legendgroup,
            showlegend=False,
        )
    )


def compound_color(compound: str) -> str:
    """Return the shared UI color for a standard or session-specific compound."""
    if compound in COMPOUND_COLORS:
        return COMPOUND_COLORS[compound]
    palette_index = sum(ord(character) for character in compound) % len(FALLBACK_COLORS)
    return FALLBACK_COLORS[palette_index]


def _with_alpha(hex_color: str, alpha: float) -> str:
    red, green, blue = (int(hex_color[index : index + 2], 16) for index in (1, 3, 5))
    return f"rgba({red},{green},{blue},{alpha})"


def _base_figure(
    figure: go.Figure,
    *,
    title: str,
    x_title: str | None,
    y_title: str | None = None,
    height: int,
    x_tickformat: str | None = None,
    y_tickformat: str | None = None,
) -> go.Figure:
    figure.update_layout(
        title={"text": title.upper(), "font": {"size": 12, "color": MUTED_COLOR}},
        height=height,
        margin={"l": 18, "r": 18, "t": 58, "b": 18},
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=PANEL_COLOR,
        font={"family": "Inter, sans-serif", "color": TEXT_COLOR, "size": 11},
        hoverlabel={"bgcolor": "#0f0f11", "font": {"color": TEXT_COLOR}},
        legend={"orientation": "h", "y": 1.08, "x": 1, "xanchor": "right"},
    )
    figure.update_xaxes(
        title=x_title,
        gridcolor=GRID_COLOR,
        zeroline=False,
        tickformat=x_tickformat,
    )
    figure.update_yaxes(
        title=y_title,
        gridcolor=GRID_COLOR,
        zeroline=False,
        tickformat=y_tickformat,
    )
    return figure
