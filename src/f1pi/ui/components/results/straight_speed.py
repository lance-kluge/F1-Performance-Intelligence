"""Straight-line observations and explicit limits on causal interpretation."""

import streamlit as st

from f1pi.analysis.models import LapComparison
from f1pi.ui.components.results.chrome import render_result_section
from f1pi.ui.straight_observations import (
    lap_identities,
    straight_speed_observations,
    straight_speed_summary,
)


def render_straight_speed(comparison: LapComparison) -> None:
    render_result_section(
        9, "Straight-line observations", "Compare speed at the entry and exit of each straight."
    )
    observations = straight_speed_observations(comparison)
    if not observations:
        st.info(straight_speed_summary(comparison, observations))
        return
    st.write(straight_speed_summary(comparison, observations))
    a, b = lap_identities(comparison)
    st.dataframe(
        [
            {
                "Straight": observation.section,
                f"{a} entry (km/h)": round(observation.lap_a_entry_kph, 1),
                f"{b} entry (km/h)": round(observation.lap_b_entry_kph, 1),
                f"{a} exit (km/h)": round(observation.lap_a_exit_kph, 1),
                f"{b} exit (km/h)": round(observation.lap_b_exit_kph, 1),
                "Exit speed advantage": observation.exit_advantage,
                "Confidence": observation.confidence.value.title(),
            }
            for observation in observations
        ],
        hide_index=True, width="stretch",
    )
    st.caption(
        "Exit speed is measured at the detected straight boundary, not necessarily "
        "the maximum speed or an official speed trap. Entry speed provides context "
        "for an advantage carried out of the preceding corner."
    )
    st.info(
        "Possible explanations to investigate include power delivery, aerodynamic drag, "
        "DRS, a tow, corner-exit speed, tires, fuel load, wind and energy deployment. "
        "This comparison does not isolate these effects or establish that either car "
        "has more engine power or less downforce."
    )
