from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

from f1pi.ui.styles import stylesheet


def test_landing_page_renders_without_platform_or_fastf1() -> None:
    sys.modules.pop("f1pi.composition", None)

    app = AppTest.from_file(Path(__file__).parents[2] / "streamlit_app.py").run()

    assert not app.exception
    assert "f1pi.composition" not in sys.modules
    assert [button.label for button in app.button] == [
        "Open lap analysis — coming next",
        "Open lap analysis — coming next",
    ]
    assert all(button.disabled for button in app.button)
    rendered_markup = " ".join(element.proto.body for element in app.get("html"))
    assert "See where the lap was won." in rendered_markup
    assert "illustrative data" in rendered_markup
    assert "Method over mythology" in rendered_markup


def test_stylesheet_contains_scoped_accessibility_rules() -> None:
    css = stylesheet()

    assert ".f1pi-wordmark" in css
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
