from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from f1pi.ui.components import landing
from f1pi.ui.pages import home
from f1pi.ui.styles import stylesheet


def test_landing_page_renders_without_platform_or_fastf1(tmp_path: Path) -> None:
    script = textwrap.dedent(
        """
        import json
        import sys
        from pathlib import Path

        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(Path(sys.argv[1])).run()
        result = {
            "has_exception": bool(app.exception),
            "composition_loaded": "f1pi.composition" in sys.modules,
            "fastf1_loaded": any(
                name == "fastf1" or name.startswith("fastf1.") for name in sys.modules
            ),
        }
        Path(sys.argv[2]).write_text(json.dumps(result), encoding="utf-8")
        """
    )
    result_path = tmp_path / "landing-page-result.json"
    subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(Path(__file__).parents[2] / "streamlit_app.py"),
            str(result_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert not result["has_exception"]
    assert not result["composition_loaded"]
    assert not result["fastf1_loaded"]


def test_landing_components_render_expected_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    rendered_sections: list[str] = []

    monkeypatch.setattr(landing.st, "html", rendered_sections.append)
    landing.render_hero_copy()
    landing.render_analysis_preview()
    landing.render_benefits()
    landing.render_analysis_choice_intro()
    landing.render_lap_analysis_choice()
    landing.render_tire_degradation_choice()
    landing.render_strategy_simulator_choice()
    landing.render_workflow()
    landing.render_methodology()
    landing.render_final_callout()

    rendered_markup = " ".join(rendered_sections)
    assert "See where the lap was won." in rendered_markup
    assert "illustrative data" in rendered_markup
    assert "Method over mythology" in rendered_markup
    assert "How did each compound evolve?" in rendered_markup
    assert "What if we stopped on another lap?" in rendered_markup
    assert "Read the lap. Understand the stint." in rendered_markup
    assert "arrives in the next release" not in rendered_markup


def test_navigation_helpers_render_page_links(monkeypatch: pytest.MonkeyPatch) -> None:
    rendered_links: list[tuple[object, str, str, str]] = []

    def page_link(page: object, *, label: str, icon: str, width: str) -> None:
        rendered_links.append((page, label, icon, width))

    monkeypatch.setattr(home.st, "page_link", page_link)
    lap_analysis = object()
    tire_degradation = object()
    strategy_simulator = object()

    home._analysis_link(lap_analysis, key="hero")
    home._tire_degradation_link(tire_degradation)
    home._strategy_simulator_link(strategy_simulator)

    assert rendered_links == [
        (lap_analysis, "Open lap analysis", ":material/arrow_forward:", "stretch"),
        (tire_degradation, "Open tire degradation", ":material/arrow_forward:", "stretch"),
        (strategy_simulator, "Open strategy simulator", ":material/arrow_forward:", "stretch"),
    ]


def test_stylesheet_contains_scoped_accessibility_rules() -> None:
    css = stylesheet()

    assert ".f1pi-wordmark" in css
    assert ".f1pi-progress" in css
    assert ".f1pi-results-guide" in css
    assert ".f1pi-compound-grid" in css
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
