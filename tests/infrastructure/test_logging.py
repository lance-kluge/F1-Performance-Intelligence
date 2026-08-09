from __future__ import annotations

import json
import logging
import sys

from f1pi.infrastructure.logging import JsonFormatter, configure_logging, log_event


def test_json_formatter_includes_context_and_exception() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord("f1pi.test", logging.INFO, __file__, 1, "loaded", (), None)
    record.context = {"session_id": "2022-01-bahrain-r"}  # type: ignore[attr-defined]
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "loaded"
    assert payload["session_id"] == "2022-01-bahrain-r"

    try:
        raise ValueError("problem")
    except ValueError:
        error_record = logging.LogRecord(
            "f1pi.test", logging.ERROR, __file__, 1, "failed", (), exc_info=sys.exc_info()
        )
    assert "ValueError" in formatter.format(error_record)


def test_logging_configuration() -> None:
    logger = logging.getLogger("f1pi")
    original_handlers = logger.handlers[:]
    logger.handlers.clear()
    try:
        configure_logging("DEBUG")
        configure_logging("INFO")
        log_event(logging.getLogger("f1pi.test"), logging.INFO, "ready", run_id="abc")
        assert len(logger.handlers) == 1
        assert logger.level == logging.INFO
    finally:
        logger.handlers[:] = original_handlers
