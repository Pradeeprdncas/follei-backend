"""Gmail auto-reply regression: loop prevention, IMAP parsing, and the
end-to-end handle_email flow with mocked transports (no real network).
"""
from __future__ import annotations

import email
from types import SimpleNamespace

import pytest

from app.services.communications import gmail_auto_reply as gar
from app.services.communications.gmail_auto_reply import GmailAutoReplyService


def _raw_email(from_addr: str, subject: str, body: str, message_id: str = "<m1@test>", extra_headers: str = "") -> bytes:
    return (
        f"From: {from_addr}\r\n"
        f"To: bot@gmail.com\r\n"
        f"Subject: {subject}\r\n"
        f"Message-ID: {message_id}\r\n"
        f"{extra_headers}"
        f"\r\n{body}\r\n"
    ).encode("utf-8")


def test_check_loop_blocks_self_bounce_noreply_and_duplicates(monkeypatch):
    svc = GmailAutoReplyService()
    monkeypatch.setattr(svc._settings, "GMAIL_MONITORED_EMAIL", "bot@gmail.com")

    assert svc.check_loop({"from": "bot@gmail.com", "subject": "hi", "message_id": "a"}) == "self_reply"
    assert svc.check_loop({"from": "no-reply@x.com", "subject": "hi", "message_id": "b"}) == "no_reply_sender"
    assert svc.check_loop({"from": "c@x.com", "subject": "Out of Office", "message_id": "d"}) == "bounce_or_auto_reply"
    assert svc.check_loop({"from": "c@x.com", "subject": "hi", "auto_submitted": "auto-replied", "message_id": "e"}) == "auto_submitted"
    assert svc.check_loop({"from": "c@x.com", "subject": "Real question", "message_id": "f"}) is None
    # Same Message-ID a second time is a duplicate.
    assert svc.check_loop({"from": "c@x.com", "subject": "Real question", "message_id": "f"}) == "duplicate_message_id"


def test_parse_message_extracts_sender_subject_and_body():
    svc = GmailAutoReplyService()
    msg = email.message_from_bytes(_raw_email("Alice <alice@customer.com>", "Pricing?", "How much is it?"))
    parsed = svc._parse_message(msg)
    assert parsed["from"] == "alice@customer.com"
    assert parsed["subject"] == "Pricing?"
    assert "How much is it?" in parsed["body"]


def test_fetch_unseen_parses_via_mock_imap():
    svc = GmailAutoReplyService()
    raw = _raw_email("alice@customer.com", "Hi", "Question here")

    class FakeIMAP:
        def select(self, mailbox): return ("OK", [b""])
        def search(self, charset, criterion): return ("OK", [b"1"])
        def fetch(self, uid, spec): return ("OK", [(b"1 (RFC822 {...}", raw)])

    parsed = svc.fetch_unseen(imap=FakeIMAP())
    assert len(parsed) == 1
    assert parsed[0]["message"]["from"] == "alice@customer.com"


@pytest.mark.asyncio
async def test_handle_email_generates_reply_and_sends(monkeypatch):
    svc = GmailAutoReplyService()
    monkeypatch.setattr(svc, "resolve_tenant", lambda sender: "tenant-123")

    async def fake_chat_pipeline(**kwargs):
        assert kwargs["tenant_id"] == "tenant-123"
        return {"answer": "Our pricing starts at $99/mo.", "conversation_id": "conv-1"}
    monkeypatch.setattr("app.services.rag.pipelines.chat.chat_pipeline", fake_chat_pipeline)

    sent = {}

    class FakeSMTP:
        def send_message(self, msg):
            sent["to"] = msg["To"]
            sent["subject"] = msg["Subject"]
            sent["auto_submitted"] = msg["Auto-Submitted"]
            sent["body"] = msg.get_content()

    parsed = {"from": "alice@customer.com", "subject": "Pricing?", "message_id": "<m@x>", "body": "How much?"}
    result = await svc.handle_email(parsed, smtp=FakeSMTP())

    assert result["auto_replied"] is True
    assert sent["to"] == "alice@customer.com"
    assert sent["subject"] == "Re: Pricing?"
    assert sent["auto_submitted"] == "auto-replied"  # our reply is marked so it won't be answered back
    assert "99/mo" in sent["body"]


@pytest.mark.asyncio
async def test_handle_email_skips_when_tenant_unresolved(monkeypatch):
    svc = GmailAutoReplyService()
    monkeypatch.setattr(svc, "resolve_tenant", lambda sender: None)
    parsed = {"from": "stranger@nowhere.com", "subject": "Hi", "message_id": "<m2@x>", "body": "hello"}
    result = await svc.handle_email(parsed, smtp=object())
    assert result["auto_replied"] is False
    assert result["reason"] == "tenant_not_found"


@pytest.mark.asyncio
async def test_handle_email_skips_loops_before_generating(monkeypatch):
    svc = GmailAutoReplyService()
    monkeypatch.setattr(svc._settings, "GMAIL_MONITORED_EMAIL", "bot@gmail.com")
    called = False
    def _resolve(sender):
        nonlocal called
        called = True
        return "t"
    monkeypatch.setattr(svc, "resolve_tenant", _resolve)
    result = await svc.handle_email({"from": "bot@gmail.com", "subject": "hi", "message_id": "<x>", "body": "b"})
    assert result["auto_replied"] is False
    assert result["reason"] == "self_reply"
    assert called is False  # short-circuited before tenant resolution / generation
