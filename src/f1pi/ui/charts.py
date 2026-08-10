"""Pure Plotly figure factories for synchronized lap comparisons."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from f1pi.analysis.models import LapComparison
from f1pi.ui.formatting import format_delta

DRIVER_A_COLOR = "#f5f3ed"
DRIVER_B_COLOR = "#ff4f47"
POSITIVE_COLOR = "#67d2a0"
MUTED_COLOR = "#aaa7a0"
GRID_COLOR = "rgba(245, 243, 237, 0.10)"
PANEL_COLOR = "#141417"
TRANSPARENT = "rgba(0,0,0,0)"


def sector_figure(comparison: LapComparison) -> go.Figure:
    values = [sector.delta_seconds for sector in comparison.sectors]
    numeric = [0.0 if value is None else value for value in values]
    labels = [format_delta(value) for value in values]
    colors = [
        MUTED_COLOR if value is None else DRIVER_B_COLOR if value >= 0 else POSITIVE_COLOR
        for value in values
    ]
    figure = go.Figure(
        go.Bar(
            x=numeric,
            y=[f"Sector {sector.sector}" for sector in comparison.sectors],
            orientation="h",
            marker_color=colors,
            text=labels,
            textposition="outside",
            hovertemplate="%{y}<br>Lap B - Lap A: %{text}<extra></extra>",
        )
    )
    figure.add_vline(x=0, line_color="rgba(245,243,237,.35)", line_width=1)
    return _base_figure(figure, "Sector delta", "Seconds", None, height=260)


def track_figure(comparison: LapComparison) -> go.Figure:
    telemetry = comparison.telemetry
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=telemetry["lap_a_x"],
            y=telemetry["lap_a_y"],
            mode="lines",
            name=f"Driver A · {comparison.lap_a.driver}",
            line={"color": DRIVER_A_COLOR, "width": 4},
            hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=telemetry["lap_b_x"],
            y=telemetry["lap_b_y"],
            mode="lines",
            name=f"Driver B · {comparison.lap_b.driver}",
            line={"color": DRIVER_B_COLOR, "width": 2},
            hoverinfo="skip",
        )
    )
    if comparison.corners:
        distances = telemetry["distance_metres"].to_numpy(dtype=float)
        marker_distance = np.array(
            [corner.distance_metres for corner in comparison.corners], dtype=float
        )
        figure.add_trace(
            go.Scatter(
                x=np.interp(marker_distance, distances, telemetry["lap_a_x"]),
                y=np.interp(marker_distance, distances, telemetry["lap_a_y"]),
                mode="markers+text",
                name="Corners",
                text=[corner.name for corner in comparison.corners],
                textposition="top center",
                marker={"color": DRIVER_B_COLOR, "size": 6},
                textfont={"color": MUTED_COLOR, "size": 9},
                hovertemplate="%{text}<extra></extra>",
            )
        )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    return _base_figure(figure, "Circuit trace", None, None, height=480)


def delta_figure(comparison: LapComparison) -> go.Figure:
    telemetry = comparison.telemetry
    figure = go.Figure(
        go.Scatter(
            x=telemetry["distance_metres"],
            y=telemetry["time_delta_seconds"],
            mode="lines",
            name="Lap B - Lap A",
            line={"color": DRIVER_B_COLOR, "width": 2.5},
            fill="tozeroy",
            fillcolor="rgba(255,79,71,.10)",
            hovertemplate="%{x:.0f} m<br>Delta %{y:+.3f}s<extra></extra>",
        )
    )
    figure.add_hline(y=0, line_color="rgba(245,243,237,.35)", line_width=1)
    for distance in _sector_boundaries(comparison):
        figure.add_vline(x=distance, line_color=GRID_COLOR, line_dash="dot")
    return _base_figure(figure, "Live time delta", "Distance (m)", "Seconds", height=330)


def speed_figure(comparison: LapComparison) -> go.Figure:
    telemetry = comparison.telemetry
    figure = go.Figure()
    for column, name, color in (
        ("lap_a_speed_kph", f"Driver A · {comparison.lap_a.driver}", DRIVER_A_COLOR),
        ("lap_b_speed_kph", f"Driver B · {comparison.lap_b.driver}", DRIVER_B_COLOR),
    ):
        figure.add_trace(
            go.Scatter(
                x=telemetry["distance_metres"],
                y=telemetry[column],
                mode="lines",
                name=name,
                line={"color": color, "width": 2},
                hovertemplate="%{x:.0f} m<br>%{y:.0f} km/h<extra></extra>",
            )
        )
    return _base_figure(figure, "Speed comparison", "Distance (m)", "km/h", height=360)


def inputs_figure(comparison: LapComparison) -> go.Figure:
    telemetry = comparison.telemetry
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        row_heights=[0.7, 0.3],
    )
    for prefix, label, color in (
        ("lap_a", f"Driver A · {comparison.lap_a.driver}", DRIVER_A_COLOR),
        ("lap_b", f"Driver B · {comparison.lap_b.driver}", DRIVER_B_COLOR),
    ):
        figure.add_trace(
            go.Scatter(
                x=telemetry["distance_metres"],
                y=telemetry[f"{prefix}_throttle_percent"],
                mode="lines",
                name=f"{label} throttle",
                line={"color": color, "width": 2},
                hovertemplate="%{x:.0f} m<br>Throttle %{y:.0f}%<extra></extra>",
            ),
            row=1,
            col=1,
        )
        brake = _brake_values(telemetry[f"{prefix}_brake"])
        if not np.isnan(brake).all():
            figure.add_trace(
                go.Scatter(
                    x=telemetry["distance_metres"],
                    y=brake,
                    mode="lines",
                    name=f"{label} brake",
                    line={"color": color, "width": 2, "shape": "hv"},
                    hovertemplate="%{x:.0f} m<br>Brake %{y:.0f}<extra></extra>",
                ),
                row=2,
                col=1,
            )
    figure.update_yaxes(title_text="Throttle %", range=[-5, 105], row=1, col=1)
    figure.update_yaxes(title_text="Brake", tickvals=[0, 1], row=2, col=1)
    return _base_figure(figure, "Driver inputs", "Distance (m)", None, height=480)


def corner_loss_figure(comparison: LapComparison) -> go.Figure | None:
    losses = normalized_corner_losses(comparison)
    if not losses:
        return None
    names = [name for name, _ in losses]
    values = [value for _, value in losses]
    figure = go.Figure(
        go.Bar(
            x=values,
            y=names,
            orientation="h",
            marker_color=DRIVER_B_COLOR,
            text=[f"+{value:.3f}s" for value in values],
            textposition="outside",
            hovertemplate="%{y}<br>Observed loss %{x:.3f}s<extra></extra>",
        )
    )
    figure.update_yaxes(autorange="reversed")
    return _base_figure(figure, "Largest corner losses", "Seconds", None, height=360)


def normalized_corner_losses(comparison: LapComparison) -> tuple[tuple[str, float], ...]:
    if comparison.delta_seconds > 0:
        signed = ((corner.name, corner.time_delta_seconds) for corner in comparison.corners)
    elif comparison.delta_seconds < 0:
        signed = ((corner.name, -corner.time_delta_seconds) for corner in comparison.corners)
    else:
        signed = ((corner.name, abs(corner.time_delta_seconds)) for corner in comparison.corners)
    positive = [(name, value) for name, value in signed if value > 1e-9]
    return tuple(sorted(positive, key=lambda item: item[1], reverse=True)[:8])


def _sector_boundaries(comparison: LapComparison) -> tuple[float, ...]:
    telemetry = comparison.telemetry
    sectors = telemetry["sector"].to_numpy(dtype=float)
    distance = telemetry["distance_metres"].to_numpy(dtype=float)
    changes = np.flatnonzero(np.diff(sectors, prepend=sectors[0]) > 0)
    return tuple(float(distance[index]) for index in changes)


def _brake_values(series: pd.Series) -> np.ndarray:
    return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float, na_value=np.nan)


def _base_figure(
    figure: go.Figure,
    title: str,
    x_title: str | None,
    y_title: str | None,
    *,
    height: int,
) -> go.Figure:
    figure.update_layout(
        title={"text": title.upper(), "font": {"size": 12, "color": MUTED_COLOR}},
        height=height,
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=TRANSPARENT,
        font={"family": "sans-serif", "color": "#f5f3ed", "size": 12},
        margin={"l": 20, "r": 26, "t": 58, "b": 30},
        legend={"orientation": "h", "y": 1.08, "x": 1, "xanchor": "right"},
        hovermode="x unified",
        hoverlabel={"bgcolor": PANEL_COLOR, "font": {"color": "#f5f3ed"}},
    )
    figure.update_xaxes(
        title_text=x_title,
        gridcolor=GRID_COLOR,
        zeroline=False,
    )
    figure.update_yaxes(title_text=y_title, gridcolor=GRID_COLOR, zeroline=False)
    return figure
