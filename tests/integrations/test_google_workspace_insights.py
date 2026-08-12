from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

from app.services.integrations.google_workspace_insights import build_gmail_insights


class _Query:
    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return [self.job]


class _Db:
    def __init__(self, job):
        self.job = job

    def query(self, _model):
        query = _Query()
        query.job = self.job
        return query


def _message(*, message_id: str, thread_id: str, sender: str, labels: list[str], subject: str) -> dict:
    return {
        "id": message_id,
        "thread_id": thread_id,
        "label_ids": labels,
        "internal_date": "1786492800000",
        "headers": {"from": sender, "subject": subject},
        "snippet": "Please review this message.",
        "body_text": "Please review this message.",
    }


def test_gmail_insights_exclude_promotions_and_require_confirmation(monkeypatch):
    tenant_id, source_id = uuid4(), uuid4()
    corpus = {"records": [
        _message(message_id="human", thread_id="human-thread", sender="Client <client@example.com>", labels=["INBOX"], subject="Project follow-up"),
        _message(message_id="promo", thread_id="promo-thread", sender="Shop <offers@example.com>", labels=["CATEGORY_PROMOTIONS"], subject="Sale"),
        _message(message_id="auto", thread_id="auto-thread", sender="no-reply@example.com", labels=["INBOX"], subject="Notification"),
    ]}
    job = SimpleNamespace(
        tenant_id=tenant_id,
        created_at=None,
        payload={"object_key": "gmail.json", "source_metadata": {"knowledge_source_id": str(source_id), "resource": "gmail"}},
    )
    monkeypatch.setattr(
        "app.services.integrations.google_workspace_insights.read_object",
        lambda _key: json.dumps(corpus).encode(),
    )

    result = build_gmail_insights(_Db(job), tenant_id=tenant_id, source_id=source_id, account_email="owner@example.com")

    assert result["needs_confirmation"] is True
    assert result["counts"] == {
        "messages_analyzed": 3,
        "threads_analyzed": 3,
        "sent_messages": 0,
        "excluded_promotions": 1,
        "excluded_automated_or_bulk": 1,
        "likely_human_threads": 1,
        "awaiting_user_reply": 1,
        "latest_message_from_user": 0,
    }
    assert result["reply_candidates"][0]["thread_id"] == "human-thread"
    assert result["reply_candidates"][0]["review_status"] == "pending"


def test_gmail_insights_exclude_job_boards_and_assistant_notifications(monkeypatch):
    tenant_id, source_id = uuid4(), uuid4()
    corpus = {"records": [
        _message(message_id="client", thread_id="client-thread", sender="Buyer <buyer@example.com>", labels=["INBOX"], subject="Can we discuss pricing?"),
        _message(message_id="naukri", thread_id="naukri-thread", sender="Recruiter <person@naukri.com>", labels=["INBOX"], subject="Job | Backend developer"),
        _message(message_id="cutshort", thread_id="cutshort-thread", sender="person@reply.cutshort.io", labels=["INBOX"], subject="RE: AI Engineer [Questionnaire]"),
        _message(message_id="assistant", thread_id="assistant-thread", sender="Assistant <owner@lindymail.ai>", labels=["INBOX"], subject="quick chat about your daily brief"),
    ]}
    job = SimpleNamespace(
        tenant_id=tenant_id,
        created_at=None,
        payload={"object_key": "gmail.json", "source_metadata": {"knowledge_source_id": str(source_id), "resource": "gmail"}},
    )
    monkeypatch.setattr(
        "app.services.integrations.google_workspace_insights.read_object",
        lambda _key: json.dumps(corpus).encode(),
    )

    result = build_gmail_insights(_Db(job), tenant_id=tenant_id, source_id=source_id, account_email="owner@example.com")

    assert result["counts"]["likely_human_threads"] == 1
    assert [item["thread_id"] for item in result["reply_candidates"]] == ["client-thread"]
    assert "reply_rate_percent" not in result["metrics"]
    assert result["metrics"]["threads_latest_from_user_percent"] == 0.0
