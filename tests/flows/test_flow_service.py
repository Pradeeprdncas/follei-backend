from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from app.services.flows.service import _next_business_time, default_graph, validate_graph


def test_default_flow_is_valid_and_email_first():
    graph = default_graph()
    assert validate_graph(graph, {"max_retries": 5}) == []
    assert graph["nodes"][0]["type"] == "trigger"
    assert {node["type"] for node in graph["nodes"]} >= {"score_branch", "send_email", "wait", "stop"}
    assert not ({node["type"] for node in graph["nodes"]} & {"whatsapp", "phone_call"})
    assert all(node["id"].startswith("NODE_") for node in graph["nodes"])
    assert len({node["id"] for node in graph["nodes"]}) == len(graph["nodes"])


def test_validation_rejects_missing_trigger_and_dangling_edges():
    graph = {"nodes": [{"key": "mail", "type": "send_email", "label": "Mail", "config": {}}], "edges": [{"source": "missing", "target": "mail"}]}
    errors = validate_graph(graph, {"max_retries": -1})
    assert any("trigger" in value.lower() for value in errors)
    assert any("email body" in value.lower() for value in errors)
    assert any("edge" in value.lower() for value in errors)
    assert any("retries" in value.lower() for value in errors)


def test_business_hours_moves_weekend_to_monday(monkeypatch):
    class FakeDb:
        def get(self, model, tenant_id):
            return SimpleNamespace(timezone="Asia/Kolkata")

    # Saturday 2026-08-01 05:00 UTC => Saturday 10:30 IST.
    result = _next_business_time(FakeDb(), uuid4(), datetime(2026, 8, 1, 5, 0))
    # Monday 09:00 IST => 03:30 UTC.
    assert result == datetime(2026, 8, 3, 3, 30)
