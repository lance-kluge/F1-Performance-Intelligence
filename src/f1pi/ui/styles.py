"""Shared, package-backed application styles."""

from __future__ import annotations

from importlib.resources import files

import streamlit as st

_STYLESHEET_PATHS = (
    "styles.css",
    "styles/workspace.css",
    "styles/results.css",
    "styles/tire_degradation.css",
    "styles/strategy_simulator.css",
)


def stylesheet() -> str:
    """Return the application stylesheet bundled with the UI package."""
    assets = files("f1pi.ui.assets")
    return "\n".join(
        assets.joinpath(path).read_text(encoding="utf-8") for path in _STYLESHEET_PATHS
    )


def load_styles() -> None:
    """Install the shared stylesheet once per Streamlit rerun."""
    st.html(f"<style>{stylesheet()}</style>")
