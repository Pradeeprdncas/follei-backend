"""Tenant-aware Gmail auto-reply regressions; no real network is used."""
from __future__ import annotations

import email
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.models.campaigns import CampaignMessage, InboundEmail
from app.models.conversations.conversation import Message
from app.models.leads.lead import Lead
from app.services.communications.email_connections import GmailMailbox
from app.services.communications.gmail_auto_reply import GmailAutoReplyService

TENANT_ID = "11111111-1111-4111-8111-111111111111"


def _mailbox(**overrides) -> GmailMailbox:
    values = {
        "connection_id": None,
        "tenant_id": TENANT_ID,
        "email_address": "bot@gmail.com",
        "app_password": "app-password",
        "sender_name": "Follei",
        "imap_host": "imap.gmail.com",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 465,
        "imap_last_uid": 0,
        "auto_reply_enabled": True,
        "allow_inbound_lead_creation": True,
    }
    values.update(overrides)
    return GmailMailbox(**values)


def _raw_email(from_addr: str, subject: str, body: str, message_id: str = "<m1@test>", extra_headers: str = "") -> bytes:
    return (
        f"From: {from_addr}\r\n"
        f"To: bot@gmail.com\r\n"
        f"Subject: {subject}\r\n"
        f"Message-ID: {message_id}\r\n"
        f"{extra_headers}"
        f"\r\n{body}\r\n"
    ).encode("utf-8")


def test_check_loop_blocks_self_bounce_noreply_and_automatic_mail():
    svc = GmailAutoReplyService()
    mailbox = _mailbox()
    assert svc.check_loop({"from": "bot@gmail.com", "subject": "hi"}, mailbox) == "self_reply"
    assert svc.check_loop({"from": "no-reply@x.com", "subject": "hi"}, mailbox) == "no_reply_sender"
    assert svc.check_loop({"from": "c@x.com", "subject": "Out of Office"}, mailbox) == "bounce_or_auto_reply"
    assert svc.check_loop({"from": "c@x.com", "subject": "hi", "auto_submitted": "auto-replied"}, mailbox) == "auto_submitted"
    assert svc.check_loop({"from": "c@x.com", "subject": "Real question"}, mailbox) is None


def test_parse_message_extracts_sender_subject_body_and_attachment():
    svc = GmailAutoReplyService()
    parsed_message = email.message_from_bytes(_raw_email("Alice <alice@customer.com>", "Pricing?", "How much is it?"))
    parsed = svc._parse_message(parsed_message)
    assert parsed["from"] == "alice@customer.com"
    assert parsed["from_name"] == "Alice"
    assert parsed["subject"] == "Pricing?"
    assert "How much is it?" in parsed["body"]


def test_fetch_unseen_parses_via_mock_imap():
    svc = GmailAutoReplyService()
    raw = _raw_email("alice@customer.com", "Hi", "Question here")

    class FakeIMAP:
        def select(self, mailbox): return ("OK", [b""])
        def uid(self, command, *args):
            if command == "search":
                return ("OK", [b"1"])
            if command == "fetch":
                return ("OK", [(b"1 (RFC822 {...}", raw)])
            return ("OK", [b""])

    parsed = svc.fetch_unseen(_mailbox(), imap=FakeIMAP())
    assert len(parsed) == 1
    assert parsed[0]["message"]["from"] == "alice@customer.com"


def test_current_uid_watermark_starts_after_existing_mail():
    svc = GmailAutoReplyService()

    class FakeIMAP:
        def status(self, mailbox, query):
            return ("OK", [b"INBOX (UIDNEXT 8210)"])

    assert svc.current_uid_watermark(_mailbox(), imap=FakeIMAP()) == 8209


def test_send_reply_unfolds_multiline_thread_headers():
    svc = GmailAutoReplyService()
    sent = {}

    class FakeSMTP:
        def send_message(self, msg):
            sent["message"] = msg

    svc.send_reply(
        _mailbox(),
        to_email="alice@customer.com",
        subject="Re: Question",
        body="Here is the answer.",
        in_reply_to="<latest@test>",
        references="<first@test>\r\n <second@test>",
        smtp=FakeSMTP(),
    )

    assert sent["message"]["In-Reply-To"] == "<latest@test>"
    assert sent["message"]["References"] == "<first@test> <second@test> <latest@test>"


class _Query:
    def __init__(self, session, model):
        self.session = session
        self.model = model

    def filter(self, *args, **kwargs):
        return self

    def limit(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return self.session.leads if self.model is Lead else []

    def first(self):
        if self.model is InboundEmail:
            return self.session.duplicate
        if self.model is CampaignMessage:
            return None
        if self.model is Message:
            return None
        return None


class _Session:
    def __init__(self, leads):
        self.leads = leads
        self.duplicate = None
        self.added = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def query(self, model):
        return _Query(self, model)

    def add(self, row):
        self.added.append(row)
        if isinstance(row, Lead):
            self.leads.append(row)

    def commit(self):
        return None

    def rollback(self):
        return None

    def refresh(self, row):
        return None

    def delete(self, row):
        return None


@pytest.mark.asyncio
async def test_handle_email_reuses_tenant_lead_and_sends(monkeypatch):
    svc = GmailAutoReplyService()
    lead = Lead(
        id=uuid4(), tenant_id=UUID(TENANT_ID), email="alice@customer.com",
        first_name="Alice", profile_data={},
    )
    session = _Session([lead])
    monkeypatch.setattr("app.database.session.SessionLocal", lambda: session)

    async def fake_handle(db, **kwargs):
        assert kwargs["tenant_id"] == TENANT_ID
        assert kwargs["lead_id"] == str(lead.id)
        assert kwargs["channel"] == "email"
        return {"reply": "Our pricing starts at $99/mo.", "conversation_id": None, "escalated": False}

    monkeypatch.setattr("app.services.agents.support.worker.handle_inbound_message", fake_handle)
    sent = {}

    class FakeSMTP:
        def send_message(self, msg):
            sent["to"] = msg["To"]
            sent["subject"] = msg["Subject"]
            sent["body"] = msg.get_content()

    parsed = {
        "from": "alice@customer.com", "from_name": "Alice",
        "subject": "Pricing?", "message_id": "<m@x>",
        "body": "How much?", "attachments": [],
    }
    result = await svc.handle_email(parsed, mailbox=_mailbox(), smtp=FakeSMTP())
    assert result["auto_replied"] is True
    assert result["lead_created"] is False
    assert sent["to"] == "alice@customer.com"
    assert sent["subject"] == "Re: Pricing?"
    assert "99/mo" in sent["body"]


@pytest.mark.asyncio
async def test_handle_email_creates_unknown_sender_as_tenant_lead(monkeypatch):
    svc = GmailAutoReplyService()
    session = _Session([])
    monkeypatch.setattr("app.database.session.SessionLocal", lambda: session)

    async def fake_handle(db, **kwargs):
        return {"reply": "Thanks for contacting us.", "conversation_id": None, "escalated": False}

    monkeypatch.setattr("app.services.agents.support.worker.handle_inbound_message", fake_handle)

    class FakeSMTP:
        def send_message(self, msg):
            pass

    parsed = {
        "from": "new@customer.com", "from_name": "New Person",
        "subject": "Hello", "message_id": "<new@x>",
        "body": "Tell me more", "attachments": [],
    }
    result = await svc.handle_email(parsed, mailbox=_mailbox(), smtp=FakeSMTP())
    assert result["auto_replied"] is True
    assert result["lead_created"] is True
    created = next(row for row in session.added if isinstance(row, Lead))
    assert created.tenant_id == UUID(TENANT_ID)
    assert created.email == "new@customer.com"
    assert created.profile_data["source"] == "inbound_email"
    assert created.profile_data["marketing_consent"] is False


@pytest.mark.asyncio
async def test_handle_email_does_not_create_when_connection_policy_disallows(monkeypatch):
    svc = GmailAutoReplyService()
    session = _Session([])
    monkeypatch.setattr("app.database.session.SessionLocal", lambda: session)
    parsed = {
        "from": "new@customer.com", "subject": "Hi",
        "message_id": "<m2@x>", "body": "hello", "attachments": [],
    }
    result = await svc.handle_email(
        parsed,
        mailbox=_mailbox(allow_inbound_lead_creation=False),
        smtp=object(),
    )
    assert result["auto_replied"] is False
    assert result["reason"] == "lead_not_found"


@pytest.mark.asyncio
async def test_handle_email_skips_loop_before_database(monkeypatch):
    svc = GmailAutoReplyService()
    called = False

    def _session():
        nonlocal called
        called = True
        return _Session([])

    monkeypatch.setattr("app.database.session.SessionLocal", _session)
    result = await svc.handle_email(
        {"from": "bot@gmail.com", "subject": "hi", "message_id": "<x>", "body": "b"},
        mailbox=_mailbox(),
    )
    assert result["auto_replied"] is False
    assert result["reason"] == "self_reply"
    assert called is False
