"""Shared headings for focused result views."""

from __future__ import annotations

from html import escape

import streamlit as st


def render_result_section(number: int, title: str, detail: str) -> None:
    """Render a numbered result-section heading with a concise reading cue."""
    st.html(
        f'<header class="f1pi-result-section"><span>{number:02d}</span><div>'
        f"<h2>{escape(title)}</h2><p>{escape(detail)}</p></div></header>"
    )
