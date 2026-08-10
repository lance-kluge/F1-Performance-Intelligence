from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from f1pi.analysis import LapComparisonEngine, LapSelection, SynchronizationConfig
from f1pi.analysis.explanation import explain_comparison
from f1pi.analysis.models import CornerComparison, LapSummary, SectorComparison
from f1pi.analysis.selection import select_lap
from f1pi.domain.exceptions import LapNotFoundError, TelemetryNotAvailableError


class MemorySession:
    def __init__(self, *, truncate_ver: bool = False, corners: bool = True) -> None:
        self._laps = pd.DataFrame(
            {
                "driver": ["NOR", "VER"],
                "lap_number": pd.array([7, 8], dtype="Int64"),
                "lap_time_ns": pd.array([10_000_000_000, 10_400_000_000], dtype="Int64"),
                "lap_start_time_ns": pd.array([0, 20_000_000_000], dtype="Int64"),
                "sector1_time_ns": pd.array([3_000_000_000, 3_050_000_000], dtype="Int64"),
                "sector2_time_ns": pd.array([3_000_000_000, 3_050_000_000], dtype="Int64"),
                "sector3_time_ns": pd.array([4_000_000_000, 4_300_000_000], dtype="Int64"),
                "is_accurate": pd.array([True, True], dtype="boolean"),
            }
        )
        self._car = {
            "NOR": _car_frame(0.0, 10.0, speed=180.0, throttle_progress=0.55),
            "VER": _car_frame(
                20.0,
                30.0 if truncate_ver else 30.4,
                speed=500 * 3.6 / 10.4,
                throttle_progress=0.60,
            ),
        }
        self._position = {
            "NOR": _position_frame(0.0, 10.0),
            "VER": _position_frame(20.0, 30.4),
        }
        self._corners = (
            pd.DataFrame(
                {
                    "number": [14],
                    "letter": [""],
                    "x": [250.0],
                    "y": [0.0],
                    "angle": [0.0],
                    "distance": [250.0],
                }
            )
            if corners
            else pd.DataFrame()
        )

    def laps(self) -> pd.DataFrame:
        return self._laps

    def car_telemetry(self, driver: str | None = None) -> pd.DataFrame:
        assert driver is not None
        return self._car[driver]

    def position(self, driver: str | None = None) -> pd.DataFrame:
        assert driver is not None
        return self._position[driver]

    def circuit_corners(self) -> pd.DataFrame:
        return self._corners


def _car_frame(start: float, end: float, *, speed: float, throttle_progress: float) -> pd.DataFrame:
    time = np.linspace(start, end, 105)
    progress = (time - start) / (end - start)
    return pd.DataFrame(
        {
            "session_time_ns": pd.array(np.rint(time * 1e9), dtype="Int64"),
            "speed": speed,
            "throttle": np.where(progress >= throttle_progress, 100, 55),
            "brake": progress < 0.5,
        }
    )


def _position_frame(start: float, end: float) -> pd.DataFrame:
    time = np.linspace(start, end, 51)
    progress = (time - start) / (end - start)
    return pd.DataFrame(
        {
            "session_time_ns": pd.array(np.rint(time * 1e9), dtype="Int64"),
            "x": progress * 500,
            "y": np.zeros(len(time)),
        }
    )


def test_complete_comparison_is_spatially_synchronized_and_explained() -> None:
    result = LapComparisonEngine().compare(
        MemorySession(), LapSelection.fastest("nor"), LapSelection.fastest("VER")
    )

    assert result.lap_a.driver == "NOR"
    assert result.lap_a.lap_number == 7
    assert result.delta_seconds == pytest.approx(0.4)
    assert [sector.delta_seconds for sector in result.sectors] == pytest.approx([0.05, 0.05, 0.3])
    assert len(result.telemetry) == 1000
    assert result.telemetry["time_delta_seconds"].iloc[0] == pytest.approx(0.0)
    assert result.telemetry["time_delta_seconds"].iloc[-1] == pytest.approx(0.4)
    assert result.telemetry["lap_a_brake"].dtype == pd.BooleanDtype()
    assert result.telemetry["sector"].dropna().unique().tolist() == [1.0, 2.0, 3.0]

    assert len(result.corners) == 1
    assert result.corners[0].name == "Turn 14"
    assert result.explanation.faster_driver == "NOR"
    assert result.explanation.largest_loss_sector == 3
    assert result.explanation.minimum_speed_advantage_kph == pytest.approx(6.923, rel=1e-3)
    assert result.explanation.earlier_full_throttle_metres == pytest.approx(25, abs=2)
    assert "Turn 14" in result.explanation.text
    assert "full throttle" in result.explanation.text


def test_explanation_preserves_evidence_when_faster_lap_is_b() -> None:
    result = LapComparisonEngine().compare(
        MemorySession(), LapSelection.fastest("VER"), LapSelection.fastest("NOR")
    )

    assert result.delta_seconds == pytest.approx(-0.4)
    assert result.telemetry["time_delta_seconds"].iloc[-1] == pytest.approx(-0.4)
    assert result.explanation.faster_driver == "NOR"
    assert result.explanation.largest_loss_sector == 3
    assert result.explanation.minimum_speed_advantage_kph == pytest.approx(6.923, rel=1e-3)
    assert result.explanation.earlier_full_throttle_metres == pytest.approx(25, abs=2)


def test_identical_laps_do_not_claim_one_driver_is_faster() -> None:
    result = LapComparisonEngine().compare(
        MemorySession(), LapSelection.fastest("NOR"), LapSelection.fastest("NOR")
    )

    assert result.delta_seconds == 0
    assert result.explanation.faster_driver is None
    assert result.explanation.slower_driver is None
    assert result.explanation.text == "The selected laps have identical recorded lap times."


def test_same_driver_explanation_distinguishes_lap_numbers() -> None:
    faster = LapSummary("NOR", 7, 90.0, (30.0, 30.0, 30.0), True)
    slower = LapSummary("NOR", 12, 90.4, (30.1, 30.1, 30.2), True)
    sectors = (
        SectorComparison(1, 30.0, 30.1, 0.1),
        SectorComparison(2, 30.0, 30.1, 0.1),
        SectorComparison(3, 30.0, 30.2, 0.2),
    )

    explanation = explain_comparison(faster, slower, sectors, ())

    assert explanation.faster_driver == "NOR lap 7"
    assert explanation.slower_driver == "NOR lap 12"
    assert explanation.text == (
        "NOR lap 7 is 0.400 seconds faster than NOR lap 12. "
        "NOR lap 12 loses approximately 0.200 seconds in Sector 3."
    )


def test_equal_time_different_laps_still_explain_local_tradeoffs() -> None:
    lap_a = LapSummary("NOR", 7, 90.0, (30.0, 30.2, 29.8), True)
    lap_b = LapSummary("NOR", 12, 90.0, (30.2, 29.9, 29.9), True)
    sectors = (
        SectorComparison(1, 30.0, 30.2, 0.2),
        SectorComparison(2, 30.2, 29.9, -0.3),
        SectorComparison(3, 29.8, 29.9, 0.1),
    )
    corners = (
        CornerComparison(14, "", 250.0, 0.05, 145.0, 148.0, 310.0, 290.0),
    )

    explanation = explain_comparison(lap_a, lap_b, sectors, corners)

    assert explanation.faster_driver is None
    assert explanation.slower_driver is None
    assert explanation.largest_loss_sector == 2
    assert explanation.key_corner == "Turn 14"
    assert explanation.minimum_speed_advantage_kph == pytest.approx(3.0)
    assert explanation.earlier_full_throttle_metres == pytest.approx(20.0)
    assert "NOR lap 7 and NOR lap 12 have identical recorded lap times" in explanation.text
    assert "NOR lap 7 loses approximately 0.300 seconds" in explanation.text
    assert "NOR lap 12 carries 3.0 km/h more minimum speed" in explanation.text
    assert "NOR lap 12 reaches full throttle 20 metres earlier" in explanation.text


def test_numbered_lap_can_include_inaccurate_data() -> None:
    session = MemorySession()
    session._laps.loc[0, "is_accurate"] = False

    with pytest.raises(LapNotFoundError):
        select_lap(session.laps(), LapSelection.numbered("NOR", 7))

    selected = select_lap(session.laps(), LapSelection.numbered("NOR", 7, accurate_only=False))
    assert selected["lap_number"] == 7


def test_fastest_selection_uses_lap_time_not_input_order() -> None:
    laps = pd.concat(
        [
            MemorySession().laps(),
            pd.DataFrame(
                {
                    "driver": ["NOR"],
                    "lap_number": [9],
                    "lap_time_ns": [9_900_000_000],
                    "lap_start_time_ns": [40_000_000_000],
                    "sector1_time_ns": [3_000_000_000],
                    "sector2_time_ns": [3_000_000_000],
                    "sector3_time_ns": [3_900_000_000],
                    "is_accurate": [True],
                }
            ),
        ],
        ignore_index=True,
    )

    assert select_lap(laps, LapSelection.fastest("NOR"))["lap_number"] == 9


def test_comparison_works_without_optional_corner_metadata() -> None:
    result = LapComparisonEngine(SynchronizationConfig(sample_count=200)).compare(
        MemorySession(corners=False),
        LapSelection.fastest("NOR"),
        LapSelection.fastest("VER"),
    )

    assert result.corners == ()
    assert result.explanation.key_corner is None
    assert "Sector 3" in result.explanation.text


def test_corner_matching_rotates_position_trace_to_marker_coordinates() -> None:
    session = MemorySession()
    session._corners = pd.DataFrame(
        {
            "number": [14],
            "letter": [""],
            "x": [0.0],
            "y": [250.0],
            "angle": [0.0],
            "distance": [250.0],
            "rotation": [90.0],
        }
    )

    result = LapComparisonEngine().compare(
        session, LapSelection.fastest("NOR"), LapSelection.fastest("VER")
    )

    assert result.corners[0].distance_metres == pytest.approx(250.0, abs=1.0)


def test_synchronization_preserves_unavailable_brake_samples() -> None:
    session = MemorySession()
    session._car["NOR"]["brake"] = pd.NA

    result = LapComparisonEngine().compare(
        session, LapSelection.fastest("NOR"), LapSelection.fastest("VER")
    )

    assert result.telemetry["lap_a_brake"].dtype == pd.BooleanDtype()
    assert result.telemetry["lap_a_brake"].isna().all()
    assert result.telemetry["lap_b_brake"].notna().all()


def test_comparison_rejects_incomplete_lap_telemetry() -> None:
    with pytest.raises(TelemetryNotAvailableError, match="does not span"):
        LapComparisonEngine().compare(
            MemorySession(truncate_ver=True),
            LapSelection.fastest("NOR"),
            LapSelection.fastest("VER"),
        )


@pytest.mark.parametrize("driver,lap_number", [("   ", None), ("NOR", 0)])
def test_lap_selection_rejects_invalid_input(driver: str, lap_number: int | None) -> None:
    with pytest.raises(ValueError):
        LapSelection(driver, lap_number=lap_number)


@pytest.mark.parametrize(
    "options",
    [
        {"sample_count": 99},
        {"corner_window_metres": 0},
        {"full_throttle_percent": 101},
    ],
)
def test_synchronization_config_rejects_invalid_values(options: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        SynchronizationConfig(**options)  # type: ignore[arg-type]
