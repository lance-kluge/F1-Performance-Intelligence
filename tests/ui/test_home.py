from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from f1pi.ui.styles import stylesheet


def test_landing_page_renders_without_platform_or_fastf1() -> None:
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
            "page_links": [link.proto.label for link in app.get("page_link")],
            "markup": " ".join(element.proto.body for element in app.get("html")),
        }
        print(json.dumps(result))
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(Path(__file__).parents[2] / "streamlit_app.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert not result["has_exception"]
    assert not result["composition_loaded"]
    assert not result["fastf1_loaded"]
    assert result["page_links"] == [
        "Open lap analysis",
        "Open lap analysis",
        "Open tire degradation",
        "Open strategy simulator",
    ]
    rendered_markup = result["markup"]
    assert "See where the lap was won." in rendered_markup
    assert "illustrative data" in rendered_markup
    assert "Method over mythology" in rendered_markup
    assert "How did each compound evolve?" in rendered_markup
    assert "What if we stopped on another lap?" in rendered_markup
    assert "Read the lap. Understand the stint." in rendered_markup
    assert "arrives in the next release" not in rendered_markup


def test_stylesheet_contains_scoped_accessibility_rules() -> None:
    css = stylesheet()

    assert ".f1pi-wordmark" in css
    assert ".f1pi-progress" in css
    assert ".f1pi-results-guide" in css
    assert ".f1pi-compound-grid" in css
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
