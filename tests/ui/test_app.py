"""Tests for the Streamlit application shell."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from f1pi.ui import app


def test_app_opens_directly_to_lap_analysis(monkeypatch: Any) -> None:
    """The default route should be a working analysis workspace, not marketing content."""
    pages: list[dict[str, object]] = []
    navigated_pages: list[object] = []
    navigation_ran = False

    def page(
        render: Callable[[], None],
        *,
        title: str,
        icon: str,
        url_path: str,
        default: bool = False,
    ) -> dict[str, object]:
        configured_page = {
            "render": render,
            "title": title,
            "icon": icon,
            "url_path": url_path,
            "default": default,
        }
        pages.append(configured_page)
        return configured_page

    class Navigation:
        def run(self) -> None:
            nonlocal navigation_ran
            navigation_ran = True

    def navigation(configured_pages: list[object], *, position: str) -> Navigation:
        assert position == "top"
        navigated_pages.extend(configured_pages)
        return Navigation()

    monkeypatch.setattr(app.st, "set_page_config", lambda **_: None)
    monkeypatch.setattr(app.st, "Page", page)
    monkeypatch.setattr(app.st, "navigation", navigation)
    monkeypatch.setattr(app, "load_styles", lambda: None)

    app.main()

    assert [page["title"] for page in pages] == [
        "Lap analysis",
        "Tire degradation",
        "Strategy simulator",
    ]
    assert pages[0]["default"] is True
    assert all(page["default"] is False for page in pages[1:])
    assert navigated_pages == pages
    assert navigation_ran
