"""Brevo SMS provider + router-selection regression.

The Brevo HTTP call is mocked (no real SMS is sent); the router test proves the
SMS_PROVIDER setting flips the "sms" channel between Twilio and Brevo without
affecting other channels.
"""
from __future__ import annotations

import httpx
import pytest

from app.services.communications.providers.brevo_sms_provider import BrevoSmsProvider
from app.services.communications.providers.sms_provider import SmsProvider
from app.services.communications.router import CommunicationRouter


def _with_settings(obj, **overrides):
    obj._settings = type(obj._settings)(**{**obj._settings.model_dump(), **overrides})
    return obj


def test_sender_is_alphanumeric_and_bounded():
    p = BrevoSmsProvider()
    assert p._sender("Follei Team Sales") == "FolleiTeamS"  # spaces stripped, <=11 chars
    assert p._sender(None)  # falls back to a non-empty default


@pytest.mark.asyncio
async def test_brevo_send_posts_to_transactional_sms_and_succeeds(monkeypatch):
    p = _with_settings(BrevoSmsProvider(), BREVO_API_KEY="test-key", BREVO_SENDER_NAME="Follei")
    captured = {}

    class FakeResponse:
        status_code = 201
        content = b'{"messageId": 12345}'
        def json(self): return {"messageId": 12345}
        text = ""

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    result = await p.send(recipient="+919876543210", body="Your demo is confirmed.")
    assert result.success is True
    assert result.provider_message_id == "12345"
    assert captured["url"].endswith("/v3/transactionalSMS/sms")
    assert captured["headers"]["api-key"] == "test-key"
    assert captured["json"]["recipient"] == "+919876543210"
    assert captured["json"]["content"] == "Your demo is confirmed."
    assert captured["json"]["type"] == "transactional"


@pytest.mark.asyncio
async def test_brevo_send_reports_http_error(monkeypatch):
    p = _with_settings(BrevoSmsProvider(), BREVO_API_KEY="test-key")

    class FakeResponse:
        status_code = 400
        content = b'{"code":"invalid_parameter"}'
        text = '{"code":"invalid_parameter"}'
        def json(self): return {}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = await p.send(recipient="+10000000000", body="hi")
    assert result.success is False
    assert "400" in result.error


@pytest.mark.asyncio
async def test_brevo_send_without_key_is_not_configured():
    p = _with_settings(BrevoSmsProvider(), BREVO_API_KEY="")
    result = await p.send(recipient="+10000000000", body="hi")
    assert result.success is False
    assert result.status == "not_configured"


def test_router_selects_sms_provider_by_setting():
    twilio_router = _with_settings(CommunicationRouter(), SMS_PROVIDER="twilio")
    brevo_router = _with_settings(CommunicationRouter(), SMS_PROVIDER="brevo")
    default_router = _with_settings(CommunicationRouter(), SMS_PROVIDER="")

    assert twilio_router._resolve_class("sms") is SmsProvider
    assert brevo_router._resolve_class("sms") is BrevoSmsProvider
    assert default_router._resolve_class("sms") is SmsProvider  # empty -> twilio default
    # An unknown value falls back to Twilio rather than erroring.
    assert _with_settings(CommunicationRouter(), SMS_PROVIDER="carrier-pigeon")._resolve_class("sms") is SmsProvider
    # Non-SMS channels are unaffected by SMS_PROVIDER.
    from app.services.communications.providers.email_provider import EmailProvider
    assert brevo_router._resolve_class("email") is EmailProvider
