from __future__ import annotations

import io
import json
import logging

from src.logging_utils import LogContext, JsonFormatter, new_request_id, setup_json_logging


def test_new_request_id_is_hex_string() -> None:
    rid = new_request_id()
    assert isinstance(rid, str)
    assert len(rid) == 32
    int(rid, 16)  # should parse


def test_json_formatter_includes_basic_fields_and_request_id() -> None:
    stream = io.StringIO()
    logger = logging.getLogger("beacon.test.json")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(ctx=LogContext(request_id="abc")))
    logger.addHandler(handler)

    logger.info("hello", extra={"extra": {"k": 1}})

    line = stream.getvalue().strip()
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "beacon.test.json"
    assert payload["msg"] == "hello"
    assert payload["request_id"] == "abc"
    assert payload["k"] == 1
    assert "ts" in payload


def test_setup_json_logging_sets_root_logger() -> None:
    stream = io.StringIO()
    root = setup_json_logging(level="WARNING", ctx=LogContext(request_id="rid"), stream=stream)
    assert root is logging.getLogger()

    logging.getLogger("x").warning("warn", extra={"extra": {"a": 2}})
    payload = json.loads(stream.getvalue().strip())
    assert payload["level"] == "WARNING"
    assert payload["a"] == 2
    assert payload["request_id"] == "rid"
