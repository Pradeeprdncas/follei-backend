"""Privacy-conscious, deterministic insights over persisted Google sync data."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.utils import parseaddr
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.knowledge.indexing_job import IndexingJob
from app.services.knowledge.object_storage import read_object


_AUTO_SENDER = re.compile(
    r"(no-?reply|do-?not-?reply|notification|alerts?|updates?|newsletter|"
    r"mailer-daemon|jobs?|recruit|security|messages-noreply|naukri\.com|"
    r"cutshort\.io|lindymail\.ai|hubspot\.com|em1\.cloudflare\.com)", re.I,
)
_AUTO_SUBJECT = re.compile(
    r"(security alert|sign[ -]?in|verification|one.?time|otp|password|job alert|"
    r"new job|job\s*\||application|questionnaire|newsletter|digest|trial|receipt|"
    r"invoice|statement|offer|sale|webinar|subscription|notification|weekly opportunities|"
    r"your .* assistant is ready|daily brief)", re.I,
)


def _timestamp(record: dict) -> datetime:
    try:
        return datetime.fromtimestamp(int(record.get("internal_date") or 0) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _is_sent(record: dict, account_email: str) -> bool:
    sender = parseaddr((record.get("headers") or {}).get("from", ""))[1].lower()
    return "SENT" in set(record.get("label_ids") or []) or sender == account_email.lower()


def _is_automated(record: dict) -> bool:
    headers = record.get("headers") or {}
    labels = set(record.get("label_ids") or [])
    return bool(
        {"CATEGORY_PROMOTIONS", "SPAM", "TRASH"} & labels
        or _AUTO_SENDER.search(headers.get("from", ""))
        or _AUTO_SUBJECT.search(headers.get("subject", ""))
        or headers.get("list-unsubscribe")
        or headers.get("precedence", "").lower() in {"bulk", "list", "junk"}
        or headers.get("auto-submitted", "").lower() not in {"", "no"}
    )


def _latest_gmail_corpus(db: Session, *, tenant_id: UUID, source_id: UUID) -> list[dict]:
    jobs = db.query(IndexingJob).filter(IndexingJob.tenant_id == tenant_id).order_by(IndexingJob.created_at.desc()).all()
    candidates: list[list[dict]] = []
    for job in jobs:
        payload = job.payload or {}
        metadata = payload.get("source_metadata") or {}
        if str(metadata.get("knowledge_source_id") or "") != str(source_id) or metadata.get("resource") != "gmail":
            continue
        object_key = payload.get("object_key")
        if not object_key:
            continue
        try:
            corpus = json.loads(read_object(object_key))
        except Exception:
            continue
        records = corpus.get("records") if isinstance(corpus, dict) else None
        if isinstance(records, list):
            candidates.append(records)
    return max(candidates, key=len, default=[])


def build_gmail_insights(db: Session, *, tenant_id: UUID, source_id: UUID, account_email: str) -> dict:
    records = _latest_gmail_corpus(db, tenant_id=tenant_id, source_id=source_id)
    threads: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        threads[str(record.get("thread_id") or record.get("id"))].append(record)
    for messages in threads.values():
        messages.sort(key=_timestamp)

    promotion_threads = {
        key for key, messages in threads.items()
        if any("CATEGORY_PROMOTIONS" in set(item.get("label_ids") or []) for item in messages)
    }
    automated_threads = {
        key for key, messages in threads.items() if any(_is_automated(item) for item in messages)
    }
    human_threads = {
        key: messages for key, messages in threads.items()
        if key not in promotion_threads | automated_threads
    }
    waiting = [messages for messages in human_threads.values() if not _is_sent(messages[-1], account_email)]
    answered = [messages for messages in human_threads.values() if _is_sent(messages[-1], account_email)]
    outbound = [item for item in records if _is_sent(item, account_email)]
    body_lengths = sorted(len((item.get("body_text") or item.get("snippet") or "").strip()) for item in outbound)

    response_hours: list[float] = []
    for messages in human_threads.values():
        for index, item in enumerate(messages):
            if _is_sent(item, account_email):
                continue
            next_sent = next((later for later in messages[index + 1:] if _is_sent(later, account_email)), None)
            if next_sent:
                response_hours.append((_timestamp(next_sent) - _timestamp(item)).total_seconds() / 3600)
    response_hours.sort()

    samples = []
    for messages in sorted(waiting, key=lambda value: _timestamp(value[-1]), reverse=True)[:20]:
        latest = messages[-1]
        headers = latest.get("headers") or {}
        sender_name, sender_email = parseaddr(headers.get("from", ""))
        samples.append({
            "thread_id": latest.get("thread_id"),
            "sender_name": sender_name or None,
            "sender_email": sender_email or None,
            "subject": headers.get("subject") or "(no subject)",
            "received_at": _timestamp(latest).isoformat(),
            "snippet": str(latest.get("snippet") or "")[:240],
            "review_status": "pending",
        })

    observations = []
    if waiting:
        observations.append({
            "key": "reply_gap",
            "severity": "needs_review",
            "message": f"{len(waiting)} likely human threads currently end with an inbound message.",
            "recommended_action": "Review candidates and draft replies; do not auto-send without approval.",
        })
    if body_lengths and sum(length < 80 for length in body_lengths):
        observations.append({
            "key": "short_replies",
            "severity": "informational",
            "message": f"{sum(length < 80 for length in body_lengths)} sent messages contain fewer than 80 characters.",
            "recommended_action": "Use business context to draft more specific replies where appropriate.",
        })

    return {
        "analysis_status": "ready" if records else "not_available",
        "needs_confirmation": bool(waiting),
        "classification_method": "gmail_labels_plus_sender_header_and_subject_heuristics",
        "counts": {
            "messages_analyzed": len(records),
            "threads_analyzed": len(threads),
            "sent_messages": len(outbound),
            "excluded_promotions": len(promotion_threads),
            "excluded_automated_or_bulk": len(automated_threads - promotion_threads),
            "likely_human_threads": len(human_threads),
            "awaiting_user_reply": len(waiting),
            "latest_message_from_user": len(answered),
        },
        "metrics": {
            # This is deliberately not named reply_rate: the latest-message
            # direction is a triage signal, not proof that every inbound
            # message required or received a reply.
            "threads_latest_from_user_percent": round(100 * len(answered) / len(human_threads), 1) if human_threads else None,
            "median_observed_reply_hours": round(response_hours[len(response_hours) // 2], 1) if response_hours else None,
            "median_sent_body_characters": body_lengths[len(body_lengths) // 2] if body_lengths else None,
        },
        "observations": observations,
        "reply_candidates": samples,
    }
