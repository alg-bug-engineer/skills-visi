"""Tests for JSON-safe serialization."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import json

from intersection_agent.utils.json_safe import to_json_safe


def test_decimal_and_datetime_are_json_serializable():
    payload = {
        "cycle_length": Decimal("120.5"),
        "query_trace": [
            {
                "raw_data": [
                    {"turn_saturation": Decimal("0.95"), "day": date(2025, 6, 1)},
                ],
            }
        ],
        "id": UUID("12345678-1234-5678-1234-567812345678"),
        "ts": datetime(2025, 6, 1, 18, 0, 0),
    }
    safe = to_json_safe(payload)
    text = json.dumps(safe, ensure_ascii=False)
    parsed = json.loads(text)
    assert parsed["cycle_length"] == 120.5
    assert parsed["query_trace"][0]["raw_data"][0]["turn_saturation"] == 0.95
    assert parsed["query_trace"][0]["raw_data"][0]["day"] == "2025-06-01"
    assert parsed["id"] == "12345678-1234-5678-1234-567812345678"
    assert parsed["ts"] == "2025-06-01T18:00:00"
