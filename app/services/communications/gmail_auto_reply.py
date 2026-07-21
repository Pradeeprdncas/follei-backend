"""Gmail auto-reply over IMAP + SMTP (app-password based).

Polls a monitored Gmail mailbox for unread mail, generates a grounded reply,
and sends it back in-thread. Deliberately stdlib-only (imaplib/smtplib/email)
so it needs no extra dependency and no Google Cloud OAuth app — it uses the
GMAIL_MONITORED_EMAIL / GMAIL_APP_PASSWORD already present in .env.

Reply text is produced by chat_pipeline() (the proven, grounded RAG path used
by the voice loop and the Support/SDR/Sales workers), NOT by EmailReplyGenerator:
that class routes through get_ai_router() -> the local GGUF model, which is not
provisioned in this environment and fails on every call. chat_pipeline() gives a
grounded, cited, actually-working reply and reuses the same conversation memory.

Loop/bounce protection mirrors app/services/communications/brevo_inbound.py:
self-sends, bounce/auto-reply subjects, RFC-3834 Auto-Submitted/Precedence
headers, and already-seen Message-IDs are all skipped so two auto-responders
can never ping-pong.
"""
from __future__ import annotations

import email
import imaplib
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any

from loguru import logger

from app.config.settings import get_settings

_BOUNCE_SUBJECT_INDICATORS = (
    "delivery status notification", "delivery failure", "mail delivery failed",
    "returned mail", "undelivered", "auto-reply", "automatic reply",
    "out of office", "vacation", "away from the office",
)
_NO_REPLY_LOCALPARTS = ("no-reply", "noreply", "do-not-reply", "donotreply", "mailer-daemon", "postmaster")


class GmailAutoReplyService:
    """Poll a Gmail mailbox and auto-reply to unread inbound mail."""

    def __init__(self):
        self._settings = get_settings()
        self._seen_message_ids: set[str] = set()

    @property
    def _app_password(self) -> str:
        # Google displays app passwords in spaced groups ("abcd efgh ijkl mnop")
        # but IMAP/SMTP login requires them with the spaces removed. The .env
        # value is stored as displayed, so normalize here.
        return (self._settings.GMAIL_APP_PASSWORD or "").replace(" ", "")

    # ── IMAP fetch (sync, stdlib) ──────────────────────────────────

    def fetch_unseen(self, imap: imaplib.IMAP4 | None = None, max_messages: int = 25) -> list[dict[str, Any]]:
        """Return up to *max_messages* parsed unread messages, newest UIDs first.

        Bounded per call so a large unread backlog is drained in batches over
        successive polls instead of pulling thousands of messages in one tick.
        `imap` is injectable for tests.
        """
        own = imap is None
        if own:
            imap = imaplib.IMAP4_SSL(self._settings.GMAIL_IMAP_HOST)
            imap.login(self._settings.GMAIL_MONITORED_EMAIL, self._app_password)
        try:
            imap.select("INBOX")
            status, data = imap.search(None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                return []
            uids = data[0].split()
            # Highest UIDs are the most recent; take a bounded, newest-first batch.
            batch = uids[-max_messages:][::-1]
            parsed: list[dict[str, Any]] = []
            for uid in batch:
                fetch_status, fetch_data = imap.fetch(uid, "(RFC822)")
                if fetch_status != "OK" or not fetch_data or not fetch_data[0]:
                    continue
                raw = fetch_data[0][1]
                message = email.message_from_bytes(raw)
                parsed.append({"uid": uid, "message": self._parse_message(message)})
            return parsed
        finally:
            if own:
                try:
                    imap.close()
                    imap.logout()
                except Exception:
                    pass

    def _parse_message(self, message: email.message.Message) -> dict[str, Any]:
        sender_email = parseaddr(message.get("From", ""))[1].lower()
        subject = str(make_header(decode_header(message.get("Subject", "")))) if message.get("Subject") else ""
        return {
            "from": sender_email,
            "subject": subject,
            "message_id": message.get("Message-ID", ""),
            "auto_submitted": (message.get("Auto-Submitted", "") or "").lower(),
            "precedence": (message.get("Precedence", "") or "").lower(),
            "body": self._extract_body(message),
        }

    @staticmethod
    def _extract_body(message: email.message.Message) -> str:
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()
            return ""
        payload = message.get_payload(decode=True)
        if payload:
            return payload.decode(message.get_content_charset() or "utf-8", errors="replace").strip()
        return str(message.get_payload() or "").strip()

    # ── Loop prevention (mirrors brevo_inbound._check_loop) ────────

    def check_loop(self, parsed: dict[str, Any]) -> str | None:
        """Return a block reason, or None if the message is safe to answer."""
        sender = parsed.get("from", "")
        if not sender:
            return "no_sender"
        if sender == (self._settings.GMAIL_MONITORED_EMAIL or "").lower():
            return "self_reply"
        localpart = sender.split("@", 1)[0]
        if any(localpart.startswith(p) for p in _NO_REPLY_LOCALPARTS):
            return "no_reply_sender"
        if parsed.get("auto_submitted") and parsed["auto_submitted"] != "no":
            return "auto_submitted"
        if parsed.get("precedence") in ("bulk", "auto_reply", "list"):
            return "bulk_precedence"
        subject = (parsed.get("subject") or "").lower()
        if any(ind in subject for ind in _BOUNCE_SUBJECT_INDICATORS):
            return "bounce_or_auto_reply"
        message_id = parsed.get("message_id") or ""
        if message_id:
            if message_id in self._seen_message_ids:
                return "duplicate_message_id"
            self._seen_message_ids.add(message_id)
            if len(self._seen_message_ids) > 100000:
                self._seen_message_ids.clear()
        return None

    # ── Tenant resolution ──────────────────────────────────────────

    def resolve_tenant(self, sender_email: str) -> str | None:
        """Map an inbound sender to a tenant (by Lead email, else configured default)."""
        from app.database.session import SessionLocal
        from app.models.leads.lead import Lead

        with SessionLocal() as db:
            lead = db.query(Lead).filter(Lead.email == sender_email).first()
            if lead:
                return str(lead.tenant_id)
        return self._settings.GMAIL_DEFAULT_TENANT_ID or None

    # ── SMTP send (sync, stdlib) ───────────────────────────────────

    def send_reply(self, *, to_email: str, subject: str, body: str, in_reply_to: str | None = None,
                   smtp: smtplib.SMTP | None = None) -> None:
        """Send a reply. `smtp` is injectable for tests."""
        msg = EmailMessage()
        msg["From"] = self._settings.GMAIL_MONITORED_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        # RFC-3834: mark our own reply as auto-generated so the other side's
        # loop-prevention (and ours) will not answer it back.
        msg["Auto-Submitted"] = "auto-replied"
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.set_content(body)

        own = smtp is None
        if own:
            smtp = smtplib.SMTP_SSL(self._settings.GMAIL_SMTP_HOST, self._settings.GMAIL_SMTP_PORT)
            smtp.login(self._settings.GMAIL_MONITORED_EMAIL, self._app_password)
        try:
            smtp.send_message(msg)
        finally:
            if own:
                try:
                    smtp.quit()
                except Exception:
                    pass

    # ── Orchestration ──────────────────────────────────────────────

    async def handle_email(self, parsed: dict[str, Any], *, smtp: smtplib.SMTP | None = None) -> dict[str, Any]:
        """Loop-check -> resolve tenant -> generate grounded reply -> send."""
        result: dict[str, Any] = {"auto_replied": False, "reason": None, "to": parsed.get("from")}

        block = self.check_loop(parsed)
        if block:
            result["reason"] = block
            logger.info(f"Gmail auto-reply skipped ({block}) from {parsed.get('from')}")
            return result

        tenant_id = self.resolve_tenant(parsed["from"])
        if not tenant_id:
            result["reason"] = "tenant_not_found"
            logger.warning(f"Gmail auto-reply: no tenant for {parsed['from']}")
            return result

        from app.services.rag.pipelines.chat import chat_pipeline
        reply = await chat_pipeline(question=parsed.get("body") or parsed.get("subject") or "", tenant_id=tenant_id)
        answer = reply.get("answer")
        if not answer:
            result["reason"] = "no_answer"
            return result

        self.send_reply(
            to_email=parsed["from"], subject=parsed.get("subject") or "",
            body=answer, in_reply_to=parsed.get("message_id") or None, smtp=smtp,
        )
        result["auto_replied"] = True
        result["conversation_id"] = reply.get("conversation_id")
        logger.info(f"Gmail auto-reply sent to {parsed['from']} (tenant={tenant_id})")
        return result

    async def poll_once(self) -> list[dict[str, Any]]:
        """Fetch unread mail and auto-reply to each. Returns per-message results."""
        if not self._settings.GMAIL_AUTO_REPLY_ENABLED:
            return []
        results = []
        for entry in self.fetch_unseen():
            try:
                results.append(await self.handle_email(entry["message"]))
            except Exception as exc:
                logger.error(f"Gmail auto-reply failed for one message: {exc}")
                results.append({"auto_replied": False, "reason": f"error: {exc}"})
        return results
