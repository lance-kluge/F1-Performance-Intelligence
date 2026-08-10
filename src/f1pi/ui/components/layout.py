"""Shared product chrome and section primitives."""

from __future__ import annotations

import streamlit as st


def render_wordmark(*, section: str | None = None) -> None:
    """Render the product identity without relying on trademarked artwork."""
    section_markup = f'<span class="f1pi-wordmark__section">{section}</span>' if section else ""
    st.html(
        f"""
        <header class="f1pi-wordmark" aria-label="F1 Performance Intelligence">
          <span class="f1pi-wordmark__signal" aria-hidden="true"></span>
          <span class="f1pi-wordmark__name">F1 Performance Intelligence</span>
          {section_markup}
        </header>
        """
    )


def render_footer() -> None:
    """Render source and trademark context shared by every page."""
    st.html(
        """
        <footer class="f1pi-footer">
          <span>Built with FastF1 · Python · Streamlit</span>
          <span>FastF1 is unofficial and is not associated with the Formula 1 companies.
          Formula 1 and related marks belong to their respective owners.</span>
        </footer>
        """
    )
