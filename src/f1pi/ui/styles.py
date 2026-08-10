"""Shared, package-backed application styles."""

from __future__ import annotations

from importlib.resources import files

import streamlit as st


def stylesheet() -> str:
    """Return the application stylesheet bundled with the UI package."""
    return files("f1pi.ui.assets").joinpath("styles.css").read_text(encoding="utf-8")


def load_styles() -> None:
    """Install the shared stylesheet once per Streamlit rerun."""
    st.html(f"<style>{stylesheet()}</style>")
