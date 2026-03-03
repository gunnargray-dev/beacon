from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.store_pagination import Cursor, decode_cursor, encode_cursor


def test_encode_decode_roundtrip() -> None:
    dt = datetime(2026, 3, 3, 12, 34, 56, tzinfo=timezone.utc)
    cur = encode_cursor(created_at=dt, item_id="evt_123")
    decoded = decode_cursor(cur)
    assert decoded == Cursor(created_at=dt, item_id="evt_123")


@pytest.mark.parametrize("value", ["", "not_base64", "e30", "eyJpZCI6ICJ4In0"])  # {}, {"id":"x"}
def test_decode_cursor_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        decode_cursor(value)
