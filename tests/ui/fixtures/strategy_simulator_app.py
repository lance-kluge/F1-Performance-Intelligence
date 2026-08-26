from __future__ import annotations

from datetime import UTC, datetime

from f1pi.domain.models import ScheduledEvent, ScheduledSession, SessionType
from f1pi.ui.pages import strategy_simulator as page
from tests.ui.strategy_test_data import strategy_run, strategy_setup


class FakeStrategyFacade:
    def list_available_events(self, year: int) -> tuple[ScheduledEvent, ...]:
        return (
            ScheduledEvent(
                year,
                1,
                "Australian Grand Prix",
                "Australia",
                "Melbourne",
                (
                    ScheduledSession(
                        SessionType.RACE,
                        "Race",
                        datetime(2026, 3, 8, 4, tzinfo=UTC),
                    ),
                ),
            ),
        )

    def load_setup(self, key):
        return strategy_setup()

    def simulate(self, setup, request, config):
        page.st.session_state["fake_strategy_request"] = request
        page.st.session_state["fake_strategy_config"] = config
        return strategy_run()


fake = FakeStrategyFacade()
page.get_strategy_analysis_facade = lambda: fake
page.available_strategy_events.clear()
page.render_strategy_simulator()

