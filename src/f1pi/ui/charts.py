"""Pure Plotly figure factories for synchronized lap comparisons."""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from numpy.typing import NDArray
from plotly.subplots import make_subplots

from f1pi.analysis.models import LapComparison, SectorComparison, StraightComparison
from f1pi.ui.formatting import MEASUREMENT_DECIMALS, MEASUREMENT_TICK_FORMAT

DRIVER_A_COLOR = "#f5f3ed"
DRIVER_B_COLOR = "#ff4f47"
MUTED_COLOR = "#aaa7a0"
NEUTRAL_COLOR = "#6f6f74"
GRID_COLOR = "rgba(245, 243, 237, 0.10)"
PANEL_COLOR = "#141417"
TRANSPARENT = "rgba(0,0,0,0)"
DOMINANCE_THRESHOLD_SECONDS = 0.001
FALLBACK_DOMINANCE_WINDOW_FRACTION = 0.03


def sector_figure(comparison: LapComparison) -> go.Figure:
    values = [sector.delta_seconds for sector in comparison.sectors]
    numeric = [
        0.0 if value is None else round(value, MEASUREMENT_DECIMALS)
        for value in values
    ]
    details = [_sector_gain_details(comparison, sector) for sector in comparison.sectors]
    largest_gain = max((abs(value) for value in numeric), default=0.0)
    axis_limit = max(0.01, largest_gain * 1.9)
    figure = go.Figure(
        go.Bar(
            x=numeric,
            y=[f"Sector {sector.sector}" for sector in comparison.sectors],
            orientation="h",
            marker_color=[detail[1] for detail in details],
            text=[detail[0] for detail in details],
            textposition="outside",
            cliponaxis=False,
            customdata=[detail[2] for detail in details],
            hovertemplate="%{customdata}<extra></extra>",
        )
    )
    figure.add_vline(x=0, line_color="rgba(245,243,237,.35)", line_width=1)
    figure.add_annotation(
        x=0,
        y=1.18,
        xref="paper",
        yref="paper",
        text=f"← {comparison.lap_b.driver} gained time",
        showarrow=False,
        xanchor="left",
        font={"color": DRIVER_B_COLOR, "size": 11},
    )
    figure.add_annotation(
        x=1,
        y=1.18,
        xref="paper",
        yref="paper",
        text=f"{comparison.lap_a.driver} gained time →",
        showarrow=False,
        xanchor="right",
        font={"color": DRIVER_A_COLOR, "size": 11},
    )
    figure = _base_figure(
        figure,
        "Sector advantage",
        "Time gained (seconds)",
        None,
        height=300,
        x_tickformat=MEASUREMENT_TICK_FORMAT,
    )
    figure.update_xaxes(range=[-axis_limit, axis_limit])
    return figure


def _sector_gain_details(
    comparison: LapComparison, sector: SectorComparison
) -> tuple[str, str, str]:
    delta = sector.delta_seconds
    sector_name = f"Sector {sector.sector}"
    if delta is None:
        return "Unavailable", MUTED_COLOR, f"{sector_name}<br>Sector timing unavailable"
    if abs(delta) < 0.5 * 10**-MEASUREMENT_DECIMALS:
        return (
            "No recorded gain",
            MUTED_COLOR,
            f"{sector_name}<br>No recorded advantage<br>{_sector_times(comparison, sector)}",
        )
    if delta > 0:
        winner, loser, color = comparison.lap_a.driver, comparison.lap_b.driver, DRIVER_A_COLOR
    else:
        winner, loser, color = comparison.lap_b.driver, comparison.lap_a.driver, DRIVER_B_COLOR
    gain = abs(delta)
    label = f"{winner} gained {gain:.{MEASUREMENT_DECIMALS}f}s on {loser}"
    return label, color, f"{sector_name}<br>{label}<br>{_sector_times(comparison, sector)}"


def _sector_times(comparison: LapComparison, sector: SectorComparison) -> str:
    def display(value: float | None) -> str:
        return "unavailable" if value is None else f"{value:.{MEASUREMENT_DECIMALS}f}s"

    return (
        f"{comparison.lap_a.driver}: {display(sector.lap_a_seconds)} · "
        f"{comparison.lap_b.driver}: {display(sector.lap_b_seconds)}"
    )


def track_figure(comparison: LapComparison) -> go.Figure:
    telemetry = comparison.telemetry
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=telemetry["lap_a_x"],
            y=telemetry["lap_a_y"],
            mode="lines",
            name="Track outline",
            line={"color": "#050506", "width": 11},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    local_delta = _local_delta_seconds(comparison)
    progress = _lap_progress(comparison)
    section_labels = _section_labels(comparison)
    classes = _dominance_classes(local_delta)
    hover = tuple(
        f"{section}<br>{lap_progress:.1f}% of lap<br>"
        f"{_local_gain_text(comparison, delta)}"
        for section, lap_progress, delta in zip(
            section_labels, progress, local_delta, strict=True
        )
    )
    legend_seen: set[int] = set()
    for start, end, dominance in _dominance_runs(classes):
        color, name = _dominance_style(comparison, dominance)
        show_legend = dominance not in legend_seen
        legend_seen.add(dominance)
        figure.add_trace(
            go.Scatter(
                x=telemetry["lap_a_x"].iloc[start : end + 1],
                y=telemetry["lap_a_y"].iloc[start : end + 1],
                mode="lines",
                name=name,
                legendgroup=str(dominance),
                legendrank={1: 10, -1: 20, 0: 30}[dominance],
                showlegend=show_legend,
                line={"color": color, "width": 5},
                text=hover[start : end + 1],
                hovertemplate="%{text}<extra></extra>",
            )
        )
    if comparison.corners:
        distances = telemetry["distance_metres"].to_numpy(dtype=float)
        marker_distance = np.array(
            [corner.distance_metres for corner in comparison.corners], dtype=float
        )
        lap_length = float(distances[-1])
        figure.add_trace(
            go.Scatter(
                x=np.interp(marker_distance, distances, telemetry["lap_a_x"]),
                y=np.interp(marker_distance, distances, telemetry["lap_a_y"]),
                mode="markers+text",
                name="Turns",
                legendrank=40,
                text=[f"T{corner.number}{corner.letter}" for corner in comparison.corners],
                textposition="top center",
                marker={
                    "color": PANEL_COLOR,
                    "line": {"color": MUTED_COLOR, "width": 1},
                    "size": 7,
                },
                textfont={"color": "#f5f3ed", "size": 9},
                customdata=[
                    f"{corner.name}<br>"
                    f"{corner.distance_metres / lap_length * 100:.1f}% of lap<br>"
                    f"{_local_gain_text(comparison, corner.time_delta_seconds)}"
                    for corner in comparison.corners
                ],
                hovertemplate="%{customdata}<extra></extra>",
            )
        )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    return _base_figure(figure, "Track dominance", None, None, height=520)


def delta_figure(comparison: LapComparison) -> go.Figure:
    telemetry = comparison.telemetry
    progress = _lap_progress(comparison)
    figure = go.Figure(
        go.Scatter(
            x=progress,
            y=telemetry["time_delta_seconds"].round(MEASUREMENT_DECIMALS),
            mode="lines",
            name="Cumulative gap · B - A",
            line={"color": DRIVER_B_COLOR, "width": 2.5},
            fill="tozeroy",
            fillcolor="rgba(255,79,71,.10)",
            customdata=_section_labels(comparison),
            hovertemplate=(
                "%{customdata}<br>%{x:.1f}% of lap<br>"
                f"Cumulative gap %{{y:+.{MEASUREMENT_DECIMALS}f}}s<extra></extra>"
            ),
        )
    )
    figure.add_hline(y=0, line_color="rgba(245,243,237,.35)", line_width=1)
    for lap_progress in _sector_boundaries_percent(comparison):
        figure.add_vline(x=lap_progress, line_color=GRID_COLOR, line_dash="dot")
    return _base_figure(
        figure,
        "Live time delta",
        "Lap progress",
        "Seconds",
        height=330,
        x_tickformat=".0f",
        y_tickformat=MEASUREMENT_TICK_FORMAT,
        x_ticksuffix="%",
        x_hoverformat=".1f",
    )


def speed_figure(comparison: LapComparison) -> go.Figure:
    telemetry = comparison.telemetry
    progress = _lap_progress(comparison)
    section_labels = _section_labels(comparison)
    figure = go.Figure()
    for column, name, color in (
        ("lap_a_speed_kph", f"Driver A · {comparison.lap_a.driver}", DRIVER_A_COLOR),
        ("lap_b_speed_kph", f"Driver B · {comparison.lap_b.driver}", DRIVER_B_COLOR),
    ):
        figure.add_trace(
            go.Scatter(
                x=progress,
                y=telemetry[column],
                mode="lines",
                name=name,
                line={"color": color, "width": 2},
                customdata=section_labels,
                hovertemplate=(
                    "%{customdata}<br>%{x:.1f}% of lap<br>"
                    "%{y:.0f} km/h<extra></extra>"
                ),
            )
        )
    return _base_figure(
        figure,
        "Speed comparison",
        "Lap progress",
        "km/h",
        height=360,
        x_tickformat=".0f",
        x_ticksuffix="%",
        x_hoverformat=".1f",
    )


def inputs_figure(comparison: LapComparison) -> go.Figure:
    telemetry = comparison.telemetry
    progress = _lap_progress(comparison)
    section_labels = _section_labels(comparison)
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
                x=progress,
                y=telemetry[f"{prefix}_throttle_percent"],
                mode="lines",
                name=f"{label} throttle",
                line={"color": color, "width": 2},
                customdata=section_labels,
                hovertemplate=(
                    "%{customdata}<br>%{x:.1f}% of lap<br>"
                    "Throttle %{y:.0f}%<extra></extra>"
                ),
            ),
            row=1,
            col=1,
        )
        brake = _brake_values(telemetry[f"{prefix}_brake"])
        if not np.isnan(brake).all():
            figure.add_trace(
                go.Scatter(
                    x=progress,
                    y=brake,
                    mode="lines",
                    name=f"{label} brake",
                    line={"color": color, "width": 2, "shape": "hv"},
                    customdata=section_labels,
                    hovertemplate=(
                        "%{customdata}<br>%{x:.1f}% of lap<br>"
                        "Brake %{y:.0f}<extra></extra>"
                    ),
                ),
                row=2,
                col=1,
            )
    figure.update_yaxes(title_text="Throttle %", range=[-5, 105], row=1, col=1)
    figure.update_yaxes(title_text="Brake", tickvals=[0, 1], row=2, col=1)
    return _base_figure(
        figure,
        "Driver inputs",
        "Lap progress",
        None,
        height=480,
        x_tickformat=".0f",
        x_ticksuffix="%",
        x_hoverformat=".1f",
    )


def corner_loss_figure(comparison: LapComparison) -> go.Figure | None:
    losses = normalized_corner_losses(comparison)
    if not losses:
        return None
    names = [name for name, _ in losses]
    values = [round(value, MEASUREMENT_DECIMALS) for _, value in losses]
    figure = go.Figure(
        go.Bar(
            x=values,
            y=names,
            orientation="h",
            marker_color=DRIVER_B_COLOR,
            text=[f"+{value:.{MEASUREMENT_DECIMALS}f}s" for value in values],
            textposition="outside",
            hovertemplate=(
                f"%{{y}}<br>Observed loss %{{x:.{MEASUREMENT_DECIMALS}f}}s"
                "<extra></extra>"
            ),
        )
    )
    figure.update_yaxes(autorange="reversed")
    return _base_figure(
        figure,
        "Largest corner losses",
        "Seconds",
        None,
        height=360,
        x_tickformat=MEASUREMENT_TICK_FORMAT,
    )


def normalized_corner_losses(comparison: LapComparison) -> tuple[tuple[str, float], ...]:
    if comparison.delta_seconds > 0:
        signed = ((corner.name, corner.time_delta_seconds) for corner in comparison.corners)
    elif comparison.delta_seconds < 0:
        signed = ((corner.name, -corner.time_delta_seconds) for corner in comparison.corners)
    else:
        signed = ((corner.name, abs(corner.time_delta_seconds)) for corner in comparison.corners)
    positive = [(name, value) for name, value in signed if value > 1e-9]
    return tuple(sorted(positive, key=lambda item: item[1], reverse=True)[:8])


def straight_loss_figure(comparison: LapComparison) -> go.Figure | None:
    losses = normalized_straight_losses(comparison)
    if not losses:
        return None
    names = [name for name, _ in losses]
    values = [round(value, MEASUREMENT_DECIMALS) for _, value in losses]
    figure = go.Figure(
        go.Bar(
            x=values,
            y=names,
            orientation="h",
            marker_color=DRIVER_B_COLOR,
            text=[f"+{value:.{MEASUREMENT_DECIMALS}f}s" for value in values],
            textposition="outside",
            hovertemplate=(
                f"%{{y}}<br>Observed loss %{{x:.{MEASUREMENT_DECIMALS}f}}s"
                "<extra></extra>"
            ),
        )
    )
    figure.update_yaxes(autorange="reversed")
    return _base_figure(
        figure,
        "Largest straight losses",
        "Seconds",
        None,
        height=360,
        x_tickformat=MEASUREMENT_TICK_FORMAT,
    )


def normalized_straight_losses(comparison: LapComparison) -> tuple[tuple[str, float], ...]:
    straights = getattr(comparison, "straights", ())
    if comparison.delta_seconds > 0:
        signed = (
            (straight.section_label, straight.time_delta_seconds) for straight in straights
        )
    elif comparison.delta_seconds < 0:
        signed = (
            (straight.section_label, -straight.time_delta_seconds) for straight in straights
        )
    else:
        signed = (
            (straight.section_label, abs(straight.time_delta_seconds))
            for straight in straights
        )
    positive = [(name, value) for name, value in signed if value > 1e-9]
    return tuple(sorted(positive, key=lambda item: item[1], reverse=True)[:8])


def dominance_shares(comparison: LapComparison) -> tuple[float, float, float]:
    """Return the percent of lap where A gained, B gained, or neither did."""
    classes = _dominance_classes(_local_delta_seconds(comparison))
    total = len(classes)
    shares = tuple(
        float(np.count_nonzero(classes == value) / total * 100) for value in (1, -1, 0)
    )
    return shares[0], shares[1], shares[2]


def _sector_boundaries_percent(comparison: LapComparison) -> tuple[float, ...]:
    telemetry = comparison.telemetry
    sectors = telemetry["sector"].to_numpy(dtype=float)
    progress = _lap_progress(comparison)
    changes = np.flatnonzero(np.diff(sectors, prepend=sectors[0]) > 0)
    return tuple(float(progress[index]) for index in changes)


def _lap_progress(comparison: LapComparison) -> NDArray[np.float64]:
    progress = comparison.telemetry["relative_distance"].to_numpy(dtype=float) * 100
    return cast(NDArray[np.float64], progress.round(MEASUREMENT_DECIMALS))


def _local_delta_seconds(comparison: LapComparison) -> NDArray[np.float64]:
    telemetry = comparison.telemetry
    if "local_time_delta_seconds" in telemetry:
        return cast(
            NDArray[np.float64],
            telemetry["local_time_delta_seconds"].to_numpy(dtype=float),
        )
    cumulative = cast(
        NDArray[np.float64], telemetry["time_delta_seconds"].to_numpy(dtype=float)
    )
    half_window = max(1, round(len(cumulative) * FALLBACK_DOMINANCE_WINDOW_FRACTION / 2))
    indices = np.arange(len(cumulative))
    before = np.maximum(0, indices - half_window)
    after = np.minimum(len(cumulative) - 1, indices + half_window)
    return cumulative[after] - cumulative[before]


def _dominance_classes(local_delta: NDArray[np.float64]) -> NDArray[np.int64]:
    return cast(
        NDArray[np.int64],
        np.where(
            local_delta > DOMINANCE_THRESHOLD_SECONDS,
            1,
            np.where(local_delta < -DOMINANCE_THRESHOLD_SECONDS, -1, 0),
        ).astype(np.int64),
    )


def _dominance_runs(classes: NDArray[np.int64]) -> tuple[tuple[int, int, int], ...]:
    starts = np.flatnonzero(np.diff(classes, prepend=classes[0]) != 0)
    boundaries = np.concatenate((np.array([0]), starts, np.array([len(classes)])))
    runs: list[tuple[int, int, int]] = []
    for index in range(len(boundaries) - 1):
        start = int(boundaries[index])
        end = int(boundaries[index + 1] - 1)
        if start > 0:
            start -= 1
        runs.append((start, end, int(classes[end])))
    return tuple(runs)


def _dominance_style(comparison: LapComparison, dominance: int) -> tuple[str, str]:
    if dominance > 0:
        return DRIVER_A_COLOR, f"{comparison.lap_a.driver} gained"
    if dominance < 0:
        return DRIVER_B_COLOR, f"{comparison.lap_b.driver} gained"
    return NEUTRAL_COLOR, "Within 0.001s"


def _local_gain_text(comparison: LapComparison, delta: float) -> str:
    if delta > DOMINANCE_THRESHOLD_SECONDS:
        return f"{comparison.lap_a.driver} gained {delta:.{MEASUREMENT_DECIMALS}f}s locally"
    if delta < -DOMINANCE_THRESHOLD_SECONDS:
        return (
            f"{comparison.lap_b.driver} gained "
            f"{abs(delta):.{MEASUREMENT_DECIMALS}f}s locally"
        )
    return "No measurable local gain"


def _section_labels(comparison: LapComparison) -> tuple[str, ...]:
    telemetry = comparison.telemetry
    distances = telemetry["distance_metres"].to_numpy(dtype=float)
    corners = tuple(sorted(comparison.corners, key=lambda corner: corner.distance_metres))
    if not corners:
        return tuple("Lap" for _ in distances)
    lap_length = float(distances[-1])
    straights = getattr(comparison, "straights", ())
    labels: list[str] = []
    for distance in distances:
        straight = next(
            (
                candidate
                for candidate in straights
                if _distance_in_straight(distance, candidate, lap_length)
            ),
            None,
        )
        if straight is not None:
            labels.append(straight.section_label)
            continue
        nearest = min(
            corners,
            key=lambda corner: min(
                abs(distance - corner.distance_metres),
                lap_length - abs(distance - corner.distance_metres),
            ),
        )
        labels.append(nearest.name)
    return tuple(labels)


def _distance_in_straight(
    distance: float, straight: StraightComparison, lap_length: float
) -> bool:
    start = straight.start_distance_metres
    end = straight.end_distance_metres
    if end >= start:
        return start <= distance <= end
    return start <= distance <= lap_length or 0.0 <= distance <= end


def _brake_values(series: pd.Series) -> np.ndarray:
    return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float, na_value=np.nan)


def _base_figure(
    figure: go.Figure,
    title: str,
    x_title: str | None,
    y_title: str | None,
    *,
    height: int,
    x_tickformat: str | None = None,
    y_tickformat: str | None = None,
    x_ticksuffix: str | None = None,
    x_hoverformat: str | None = None,
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
        tickformat=x_tickformat,
        ticksuffix=x_ticksuffix,
        hoverformat=x_hoverformat,
        zeroline=False,
    )
    figure.update_yaxes(
        title_text=y_title,
        gridcolor=GRID_COLOR,
        tickformat=y_tickformat,
        zeroline=False,
    )
    return figure
