"""Regression: the email inbound webhook wires a real payload to the Support worker."""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import channels_email

client = TestClient(app)


def test_inbound_email_calls_the_support_worker_and_returns_its_reply(monkeypatch):
    async def fake_handle(db, *, tenant_id, text, session_id=None, channel="email"):
        assert tenant_id == "tenant-a"
        assert text == "What is the refund window?"
        assert channel == "email"
        return {"conversation_id": "conv-1", "intent": "question", "escalated": False, "escalation_reason": None, "reply": "45 days.", "confidence": 0.9, "citations": []}

    monkeypatch.setattr(channels_email, "handle_inbound_message", fake_handle)

    resp = client.post(
        "/channels/email/inbound",
        json={"tenant_id": "tenant-a", "from_address": "customer@example.com", "subject": "Refund question", "body": "What is the refund window?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "45 days."
    assert body["escalated"] is False
    assert body["subject"] == "Re: Refund question"
    assert body["from"] == "customer@example.com"


def test_inbound_email_rejects_bad_webhook_secret(monkeypatch):
    monkeypatch.setattr(channels_email._settings, "EMAIL_INBOUND_WEBHOOK_SECRET", "expected-secret")
    resp = client.post(
        "/channels/email/inbound",
        json={"tenant_id": "tenant-a", "from_address": "customer@example.com", "body": "hello"},
        headers={"X-Webhook-Secret": "wrong-secret"},
    )
    assert resp.status_code == 401
    monkeypatch.setattr(channels_email._settings, "EMAIL_INBOUND_WEBHOOK_SECRET", "")


def test_inbound_email_accepts_correct_webhook_secret(monkeypatch):
    monkeypatch.setattr(channels_email._settings, "EMAIL_INBOUND_WEBHOOK_SECRET", "expected-secret")

    async def fake_handle(db, **_kwargs):
        return {"conversation_id": "conv-2", "intent": "question", "escalated": False, "escalation_reason": None, "reply": "ok"}

    monkeypatch.setattr(channels_email, "handle_inbound_message", fake_handle)

    resp = client.post(
        "/channels/email/inbound",
        json={"tenant_id": "tenant-a", "from_address": "customer@example.com", "body": "hello"},
        headers={"X-Webhook-Secret": "expected-secret"},
    )
    assert resp.status_code == 200
    monkeypatch.setattr(channels_email._settings, "EMAIL_INBOUND_WEBHOOK_SECRET", "")
