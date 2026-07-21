"""run_worker() dispatch regression: routing by worker_type and the
stage-gated SDR->Sales auto-handoff.

The individual worker handlers are stubbed here — this verifies the
orchestrator's routing/handoff logic in isolation, not the workers' internals
(those are covered by test_sdr_worker.py / test_sales_worker.py).
"""
from __future__ import annotations

import pytest

from app.services.agents import orchestrator


@pytest.mark.asyncio
async def test_run_worker_rejects_undispatchable_type():
    with pytest.raises(ValueError):
        await orchestrator.run_worker(None, worker_type="executive", tenant_id="t", text="hi")


@pytest.mark.asyncio
async def test_run_worker_routes_to_support(monkeypatch):
    async def fake_support(db, **kwargs):
        return {"worker": "support", "reply": "support reply", "kwargs": kwargs}
    monkeypatch.setattr(
        "app.services.agents.support.worker.handle_inbound_message", fake_support,
    )
    result = await orchestrator.run_worker(
        object(), worker_type="support", tenant_id="t1", text="help me", session_id="s1", channel="email",
    )
    assert result["worker"] == "support"
    # Support worker takes no lead_id — orchestrator must not pass one.
    assert "lead_id" not in result["kwargs"]


@pytest.mark.asyncio
async def test_sdr_without_qualification_does_not_hand_off(monkeypatch):
    async def fake_sdr(db, **kwargs):
        return {"worker": "sdr", "reply": "sdr reply", "handoff_to_sales": False}
    sales_called = False
    async def fake_sales(db, **kwargs):
        nonlocal sales_called
        sales_called = True
        return {"worker": "sales", "reply": "sales reply"}
    monkeypatch.setattr("app.services.agents.sdr.worker.handle_sdr_turn", fake_sdr)
    monkeypatch.setattr("app.services.agents.sales.worker.handle_sales_turn", fake_sales)

    result = await orchestrator.run_worker(
        object(), worker_type="sdr", tenant_id="t1", text="just browsing", lead_id="l1",
    )
    assert result["worker"] == "sdr"
    assert sales_called is False


@pytest.mark.asyncio
async def test_sdr_qualification_auto_hands_off_to_sales(monkeypatch):
    async def fake_sdr(db, **kwargs):
        return {"worker": "sdr", "reply": "sdr reply", "handoff_to_sales": True, "lead_score": 88.0}
    async def fake_sales(db, **kwargs):
        return {"worker": "sales", "reply": "sales reply", "actions": []}
    monkeypatch.setattr("app.services.agents.sdr.worker.handle_sdr_turn", fake_sdr)
    monkeypatch.setattr("app.services.agents.sales.worker.handle_sales_turn", fake_sales)

    result = await orchestrator.run_worker(
        object(), worker_type="sdr", tenant_id="t1", text="we have budget and want to buy", lead_id="l1",
    )
    # The Sales result is returned (its reply is what gets spoken), tagged with
    # the handoff and carrying the SDR result for observability.
    assert result["worker"] == "sales"
    assert result["reply"] == "sales reply"
    assert result["handed_off_from"] == "sdr"
    assert result["sdr_result"]["worker"] == "sdr"
