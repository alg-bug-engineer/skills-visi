from __future__ import annotations

from app.data.diagnosis_prefetch import (
    apply_diagnosis_prefetch,
    build_prefetch_ticket,
)


def test_build_prefetch_ticket_requires_explicit_routing_fields(monkeypatch):
    def _enrich(ticket, *, user_input=""):
        return {**ticket, "inter_id": "target-1", "intersection_name": "坤顺路与奥体西路路口"}

    monkeypatch.setattr("app.data.intersection_registry.enrich_ticket", _enrich)
    ticket = build_prefetch_ticket(
        "坤顺路与奥体西路路口，晚高峰十七点到十九点，北进口左转排队溢出。"
    )

    assert ticket is not None
    assert ticket["inter_id"] == "target-1"
    assert ticket["direction"] == "北向南"
    assert ticket["movement"] == "左转"
    assert ticket["time_range"] == "17:00-19:00"
    assert build_prefetch_ticket("帮我看看这个路口为什么堵") is None


def test_apply_prefetch_reuses_only_exact_ticket_signature():
    ticket = {
        "inter_id": "target-1",
        "direction": "北向南",
        "movement": "左转",
        "time_range": "17:00-19:00",
    }
    prefetched = {
        "ticket": dict(ticket),
        "task": {"diagnosis_ticket": ticket, "pg_raw": {"inter": "loaded"}},
        "resolved": {"ok": True, "source": "pg", "metrics": {}, "topology": {}},
    }
    task: dict = {"diagnosis_ticket": ticket}

    assert apply_diagnosis_prefetch(task, ticket, prefetched) is True
    assert task["pg_raw"] == {"inter": "loaded"}
    assert task["_diagnosis_prefetch_resolved"]["source"] == "pg"

    changed = {**ticket, "movement": "直行"}
    untouched: dict = {"diagnosis_ticket": changed}
    assert apply_diagnosis_prefetch(untouched, changed, prefetched) is False
    assert "pg_raw" not in untouched

