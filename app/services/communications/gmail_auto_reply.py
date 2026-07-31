"""Tenant-aware Gmail IMAP/SMTP ingestion and grounded auto-reply."""
from __future__ import annotations

import email
import hashlib
import imaplib
import re
import smtplib
from datetime import datetime
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr
from typing import Any
from uuid import UUID, uuid4

from loguru import logger
from sqlalchemy.exc import IntegrityError

from app.config.settings import get_settings
from app.models.campaigns import CampaignMessage, DeliveryStatus, InboundEmail
from app.models.conversations.conversation import Message, MessageAttachment
from app.models.integrations.email_connection import TenantEmailConnection
from app.models.leads.lead import Lead
from app.services.communications.email_attachment_ingestion import (
    EmailAttachmentRejected,
    queue_email_attachment,
)
from app.services.communications.email_connections import GmailMailbox, gmail_mailboxes

_BOUNCE_SUBJECT_INDICATORS = (
    "delivery status notification", "delivery failure", "mail delivery failed",
    "returned mail", "undelivered", "auto-reply", "automatic reply",
    "out of office", "vacation", "away from the office",
)
_NO_REPLY_LOCALPARTS = (
    "no-reply", "noreply", "do-not-reply", "donotreply",
    "mailer-daemon", "postmaster",
)


class GmailAutoReplyService:
    """Poll every configured Gmail connection and process lead replies."""

    def __init__(self):
        self._settings = get_settings()
        self._seen_message_ids: set[str] = set()

    # -- IMAP ---------------------------------------------------------

    def fetch_unseen(
        self,
        mailbox: GmailMailbox,
        imap: imaplib.IMAP4 | None = None,
        max_messages: int = 25,
    ) -> list[dict[str, Any]]:
        own = imap is None
        if own:
            imap = imaplib.IMAP4_SSL(mailbox.imap_host)
            imap.login(mailbox.email_address, mailbox.app_password)
        try:
            imap.select("INBOX")
            start_uid = int(mailbox.imap_last_uid or 0) + 1
            status, data = imap.uid("search", None, "UID", f"{start_uid}:*", "UNSEEN")
            if status != "OK" or not data or not data[0]:
                return []
            batch = data[0].split()[:max_messages]
            result: list[dict[str, Any]] = []
            for uid in batch:
                fetch_status, fetch_data = imap.uid("fetch", uid, "(RFC822)")
                if fetch_status != "OK" or not fetch_data or not fetch_data[0]:
                    continue
                message = email.message_from_bytes(fetch_data[0][1])
                result.append({
                    "uid": uid.decode("ascii", errors="ignore") if isinstance(uid, bytes) else str(uid),
                    "message": self._parse_message(message),
                })
            return result
        finally:
            if own:
                try:
                    imap.close()
                    imap.logout()
                except Exception:
                    pass

    def mark_seen(self, mailbox: GmailMailbox, uid: str, imap: imaplib.IMAP4 | None = None) -> None:
        own = imap is None
        if own:
            imap = imaplib.IMAP4_SSL(mailbox.imap_host)
            imap.login(mailbox.email_address, mailbox.app_password)
        try:
            imap.select("INBOX")
            imap.uid(
                "store",
                uid.encode() if isinstance(uid, str) else uid,
                "+FLAGS",
                "\\Seen",
            )
        finally:
            if own:
                try:
                    imap.close()
                    imap.logout()
                except Exception:
                    pass

    def current_uid_watermark(
        self,
        mailbox: GmailMailbox,
        imap: imaplib.IMAP4 | None = None,
    ) -> int:
        """Return the highest UID that existed when a mailbox was connected."""
        own = imap is None
        if own:
            imap = imaplib.IMAP4_SSL(mailbox.imap_host)
            imap.login(mailbox.email_address, mailbox.app_password)
        try:
            status, data = imap.status("INBOX", "(UIDNEXT)")
            raw = b" ".join(data or []).decode("ascii", errors="ignore") if status == "OK" else ""
            match = re.search(r"UIDNEXT\s+(\d+)", raw, flags=re.IGNORECASE)
            if not match:
                raise RuntimeError("Gmail did not return UIDNEXT")
            return max(0, int(match.group(1)) - 1)
        finally:
            if own:
                try:
                    imap.logout()
                except Exception:
                    pass

    @staticmethod
    def _store_uid_watermark(mailbox: GmailMailbox, uid: int) -> None:
        if not mailbox.connection_id:
            return
        from app.database.session import SessionLocal
        with SessionLocal() as db:
            row = db.get(TenantEmailConnection, UUID(mailbox.connection_id))
            if row and (row.imap_last_uid is None or int(row.imap_last_uid) < int(uid)):
                row.imap_last_uid = int(uid)
                db.commit()

    def _parse_message(self, message: email.message.Message) -> dict[str, Any]:
        sender_name, sender_email = parseaddr(message.get("From", ""))
        subject = str(make_header(decode_header(message.get("Subject", "")))) if message.get("Subject") else ""
        body, attachments = self._extract_body_and_attachments(message)
        return {
            "from": sender_email.strip().lower(),
            "from_name": sender_name.strip(),
            "to": parseaddr(message.get("To", ""))[1].strip().lower(),
            "subject": subject,
            "message_id": (message.get("Message-ID", "") or "").strip(),
            "in_reply_to": (message.get("In-Reply-To", "") or "").strip(),
            "references": (message.get("References", "") or "").strip(),
            "auto_submitted": (message.get("Auto-Submitted", "") or "").lower(),
            "precedence": (message.get("Precedence", "") or "").lower(),
            "body": body,
            "attachments": attachments,
        }

    @staticmethod
    def _extract_body_and_attachments(message: email.message.Message) -> tuple[str, list[dict[str, Any]]]:
        plain = ""
        html = ""
        attachments: list[dict[str, Any]] = []
        parts = message.walk() if message.is_multipart() else (message,)
        for part in parts:
            if part.is_multipart():
                continue
            content_disposition = str(part.get("Content-Disposition") or "").lower()
            filename_value = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if filename_value or "attachment" in content_disposition:
                filename = str(make_header(decode_header(filename_value or "attachment")))
                if payload:
                    attachments.append({
                        "filename": filename,
                        "content_type": part.get_content_type(),
                        "content_bytes": payload,
                    })
                continue
            if part.get_content_type() == "text/plain" and not plain and payload:
                plain = payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()
            elif part.get_content_type() == "text/html" and not html and payload:
                html = payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()
        # Plain text is authoritative. HTML is retained only as a bounded,
        # tag-stripped fallback so it cannot inject markup into prompts.
        if plain:
            return plain[:100_000], attachments
        if html:
            import re
            return re.sub(r"<[^>]+>", " ", html)[:100_000].strip(), attachments
        return "", attachments

    # -- policy -------------------------------------------------------

    def check_loop(self, parsed: dict[str, Any], mailbox: GmailMailbox) -> str | None:
        sender = parsed.get("from", "")
        if not sender:
            return "no_sender"
        if sender == mailbox.email_address:
            return "self_reply"
        localpart = sender.split("@", 1)[0]
        if any(localpart.startswith(prefix) for prefix in _NO_REPLY_LOCALPARTS):
            return "no_reply_sender"
        if parsed.get("auto_submitted") and parsed["auto_submitted"] != "no":
            return "auto_submitted"
        if parsed.get("precedence") in ("bulk", "auto_reply", "list"):
            return "bulk_precedence"
        subject = (parsed.get("subject") or "").lower()
        if any(indicator in subject for indicator in _BOUNCE_SUBJECT_INDICATORS):
            return "bounce_or_auto_reply"
        return None

    @staticmethod
    def _lead_for_sender(db, mailbox: GmailMailbox, parsed: dict[str, Any]) -> tuple[Lead | None, bool]:
        sender = parsed["from"].strip().lower()
        candidates = db.query(Lead).filter(
            Lead.tenant_id == UUID(mailbox.tenant_id),
        ).limit(10_000).all()
        lead = next(
            (
                row for row in candidates
                if row.email.strip().lower() == sender
                and not (row.profile_data or {}).get("merged_into")
            ),
            None,
        )
        if lead:
            return lead, False
        if not mailbox.allow_inbound_lead_creation:
            return None, False
        name_parts = (parsed.get("from_name") or "").strip().split(" ", 1)
        lead = Lead(
            id=uuid4(),
            tenant_id=UUID(mailbox.tenant_id),
            email=sender,
            first_name=name_parts[0] if name_parts else None,
            last_name=name_parts[1] if len(name_parts) > 1 else None,
            status="new",
            profile_data={
                "source": "inbound_email",
                "marketing_consent": False,
                "inbound_mailbox": mailbox.email_address,
            },
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead, True

    @staticmethod
    def _thread_key(parsed: dict[str, Any], provider_message_id: str) -> str:
        references = str(parsed.get("references") or "").split()
        if references:
            return references[0]
        return str(parsed.get("in_reply_to") or provider_message_id)

    @staticmethod
    def _normalized_subject(value: str | None) -> str:
        subject = (value or "").strip().lower()
        while subject.startswith(("re:", "fw:", "fwd:")):
            subject = subject.split(":", 1)[1].strip()
        return " ".join(subject.split())

    @staticmethod
    def _safe_message_ids(value: str | None) -> str:
        """Unfold RFC headers before assigning them to EmailMessage."""
        return " ".join((value or "").split())

    # -- SMTP ---------------------------------------------------------

    def send_reply(
        self,
        mailbox: GmailMailbox,
        *,
        to_email: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        references: str | None = None,
        smtp: smtplib.SMTP | None = None,
    ) -> str:
        msg = EmailMessage()
        msg["From"] = mailbox.email_address
        msg["To"] = to_email
        msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        msg["Message-ID"] = make_msgid(domain=mailbox.email_address.split("@", 1)[-1])
        msg["Auto-Submitted"] = "auto-replied"
        if in_reply_to:
            safe_in_reply_to = self._safe_message_ids(in_reply_to)
            safe_references = self._safe_message_ids(references)
            msg["In-Reply-To"] = safe_in_reply_to
            msg["References"] = " ".join(filter(None, [safe_references, safe_in_reply_to]))
        msg.set_content(body)
        own = smtp is None
        if own:
            if mailbox.smtp_port == 465:
                smtp = smtplib.SMTP_SSL(mailbox.smtp_host, mailbox.smtp_port)
            else:
                smtp = smtplib.SMTP(mailbox.smtp_host, mailbox.smtp_port)
                smtp.starttls()
            smtp.login(mailbox.email_address, mailbox.app_password)
        try:
            smtp.send_message(msg)
        finally:
            if own:
                try:
                    smtp.quit()
                except Exception:
                    pass
        return str(msg["Message-ID"] or "")

    # -- orchestration ------------------------------------------------

    async def handle_email(
        self,
        parsed: dict[str, Any],
        *,
        mailbox: GmailMailbox,
        smtp: smtplib.SMTP | None = None,
    ) -> dict[str, Any]:
        from app.database.session import SessionLocal
        from app.services.agents.support.worker import handle_inbound_message

        result: dict[str, Any] = {
            "auto_replied": False,
            "reason": None,
            "to": parsed.get("from"),
            "tenant_id": mailbox.tenant_id,
        }
        block = self.check_loop(parsed, mailbox)
        if block:
            result["reason"] = block
            return result
        if not mailbox.auto_reply_enabled:
            result["reason"] = "auto_reply_disabled"
            return result

        fallback_identity = "\n".join((
            mailbox.email_address,
            str(parsed.get("from") or ""),
            str(parsed.get("subject") or ""),
            str(parsed.get("body") or ""),
        ))
        provider_message_id = parsed.get("message_id") or (
            "gmail-uidless:" + hashlib.sha256(fallback_identity.encode("utf-8")).hexdigest()
        )
        with SessionLocal() as db:
            duplicate = db.query(InboundEmail).filter(
                InboundEmail.tenant_id == UUID(mailbox.tenant_id),
                InboundEmail.provider == "gmail",
                InboundEmail.provider_message_id == provider_message_id,
            ).first()
            if duplicate and duplicate.status != "failed":
                result.update({
                    "reason": "duplicate_message_id",
                    "conversation_id": str(duplicate.conversation_id) if duplicate.conversation_id else None,
                })
                return result
            if duplicate:
                db.delete(duplicate)
                db.commit()

            lead, created = self._lead_for_sender(db, mailbox, parsed)
            if not lead:
                result["reason"] = "lead_not_found"
                return result
            result["lead_id"] = str(lead.id)
            result["lead_created"] = created
            # A real inbound reply is authoritative: stop active nurture
            # enrollments before generating the response, preventing a queued
            # follow-up from racing the human conversation.
            try:
                from app.services.flows.service import stop_for_reply
                result["flow_enrollments_stopped"] = stop_for_reply(db, mailbox.tenant_id, lead.id, "email")
            except Exception:
                logger.exception("Unable to stop flow enrollment for inbound reply")

            inbound = InboundEmail(
                id=uuid4(),
                tenant_id=UUID(mailbox.tenant_id),
                lead_id=lead.id,
                from_email=parsed.get("from"),
                to_email=mailbox.email_address,
                subject=parsed.get("subject"),
                body=parsed.get("body"),
                provider="gmail",
                provider_message_id=provider_message_id,
                event_type="inbound",
                status="processing",
                raw_payload={
                    "message_id": provider_message_id,
                    "in_reply_to": parsed.get("in_reply_to"),
                    "references": parsed.get("references"),
                    "attachment_count": len(parsed.get("attachments") or []),
                },
                metadata_={"mailbox_connection_id": mailbox.connection_id},
            )
            db.add(inbound)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                result["reason"] = "duplicate_message_id"
                return result

            attachment_records: list[dict[str, Any]] = []
            for attachment in parsed.get("attachments") or []:
                try:
                    record = queue_email_attachment(
                        db,
                        tenant_id=mailbox.tenant_id,
                        lead_id=str(lead.id),
                        provider_message_id=provider_message_id,
                        filename=attachment["filename"],
                        content_type=attachment.get("content_type"),
                        content_bytes=attachment["content_bytes"],
                    )
                except EmailAttachmentRejected as exc:
                    record = {
                        "filename": attachment.get("filename"),
                        "content_type": attachment.get("content_type"),
                        "size_bytes": len(attachment.get("content_bytes") or b""),
                        "status": "rejected",
                        "error": str(exc),
                    }
                except Exception as exc:
                    logger.exception("Inbound attachment queue failed")
                    record = {
                        "filename": attachment.get("filename"),
                        "content_type": attachment.get("content_type"),
                        "size_bytes": len(attachment.get("content_bytes") or b""),
                        "status": "failed",
                        "error": str(exc)[:500],
                    }
                attachment_records.append(record)

            question = (parsed.get("body") or parsed.get("subject") or "Please review the attached document.").strip()
            support_result = await handle_inbound_message(
                db,
                tenant_id=mailbox.tenant_id,
                text=question,
                session_id=self._thread_key(parsed, provider_message_id),
                channel="email",
                lead_id=str(lead.id),
            )
            answer = support_result.get("reply")
            conversation_id = support_result.get("conversation_id")
            if not answer:
                inbound.status = "needs_human"
                inbound.metadata_ = {**(inbound.metadata_ or {}), "attachments": attachment_records}
                db.commit()
                result["reason"] = "no_answer"
                return result

            if mailbox.auth_type == "oauth":
                from app.services.communications.gmail_oauth import GmailOAuthService
                oauth_result = await GmailOAuthService().send_for_tenant(
                    tenant_id=mailbox.tenant_id,
                    to_email=parsed["from"],
                    subject=(
                        parsed.get("subject")
                        if str(parsed.get("subject") or "").lower().startswith("re:")
                        else f"Re: {parsed.get('subject') or 'your message'}"
                    ),
                    body=answer,
                    in_reply_to=provider_message_id,
                    references=parsed.get("references"),
                    thread_id=parsed.get("_gmail_thread_id"),
                )
                outbound_provider_message_id = str(oauth_result.get("message_id") or "")
            else:
                outbound_provider_message_id = self.send_reply(
                    mailbox,
                    to_email=parsed["from"],
                    subject=parsed.get("subject") or "your message",
                    body=answer,
                    in_reply_to=provider_message_id,
                    references=parsed.get("references"),
                    smtp=smtp,
                )

            inbound.conversation_id = UUID(conversation_id) if conversation_id else None
            inbound.status = "replied"
            inbound.metadata_ = {
                **(inbound.metadata_ or {}),
                "attachments": attachment_records,
                "lead_created": created,
                "escalated": bool(support_result.get("escalated")),
            }
            if conversation_id:
                inbound_message = db.query(Message).filter(
                    Message.tenant_id == UUID(mailbox.tenant_id),
                    Message.conversation_id == UUID(conversation_id),
                    Message.direction == "inbound",
                ).order_by(Message.created_at.desc()).first()
                if inbound_message:
                    inbound_message.metadata_ = {
                        **(inbound_message.metadata_ or {}),
                        "email_subject": parsed.get("subject"),
                        "provider_message_id": provider_message_id,
                        "attachments": attachment_records,
                    }
                    for record in attachment_records:
                        db.add(MessageAttachment(
                            tenant_id=UUID(mailbox.tenant_id),
                            message_id=inbound_message.id,
                            file_name=record.get("filename"),
                            file_url=record.get("object_key"),
                            content_type=record.get("content_type"),
                            metadata_=record,
                        ))
                outbound_message = db.query(Message).filter(
                    Message.tenant_id == UUID(mailbox.tenant_id),
                    Message.conversation_id == UUID(conversation_id),
                    Message.direction == "outbound",
                ).order_by(Message.created_at.desc()).first()
                if outbound_message:
                    outbound_message.metadata_ = {
                        **(outbound_message.metadata_ or {}),
                        "email_subject": f"Re: {parsed.get('subject') or 'your message'}",
                        "provider_message_id": outbound_provider_message_id,
                        "in_reply_to": provider_message_id,
                    }

            campaign_candidates = db.query(CampaignMessage).filter(
                CampaignMessage.lead_id == lead.id,
                CampaignMessage.recipient == lead.email,
            ).order_by(CampaignMessage.created_at.desc()).limit(20).all()
            inbound_subject = self._normalized_subject(parsed.get("subject"))
            reply_headers = f"{parsed.get('in_reply_to') or ''} {parsed.get('references') or ''}"
            latest_campaign_message = next(
                (
                    item for item in campaign_candidates
                    if (
                        inbound_subject
                        and self._normalized_subject(item.subject) == inbound_subject
                    )
                    or (
                        item.provider_message_id
                        and item.provider_message_id in reply_headers
                    )
                ),
                None,
            )
            if latest_campaign_message:
                inbound.campaign_id = latest_campaign_message.campaign_id
                latest_campaign_message.status = DeliveryStatus.REPLIED
                latest_campaign_message.replied_at = datetime.utcnow()
            db.commit()

            result.update({
                "auto_replied": True,
                "conversation_id": conversation_id,
                "attachment_count": len(attachment_records),
                "attachments": [
                    {key: value for key, value in item.items() if key != "object_key"}
                    for item in attachment_records
                ],
            })
            return result

    def _update_connection_health(self, mailbox: GmailMailbox, error: str | None) -> None:
        if not mailbox.connection_id:
            return
        from app.database.session import SessionLocal
        with SessionLocal() as db:
            row = db.get(TenantEmailConnection, UUID(mailbox.connection_id))
            if row:
                row.last_polled_at = datetime.utcnow()
                row.last_error = error[:2000] if error else None
                row.status = "error" if error else "active"
                row.verified = not bool(error)
                db.commit()

    @staticmethod
    def _mark_inbound_failed(mailbox: GmailMailbox, parsed: dict[str, Any], error: Exception) -> None:
        message_id = parsed.get("message_id")
        if not message_id:
            return
        from app.database.session import SessionLocal
        with SessionLocal() as db:
            row = db.query(InboundEmail).filter(
                InboundEmail.tenant_id == UUID(mailbox.tenant_id),
                InboundEmail.provider == "gmail",
                InboundEmail.provider_message_id == message_id,
            ).first()
            if row:
                row.status = "failed"
                row.metadata_ = {**(row.metadata_ or {}), "last_error": str(error)[:1000]}
                db.commit()

    async def poll_once(self) -> list[dict[str, Any]]:
        from app.database.session import SessionLocal

        with SessionLocal() as db:
            mailboxes = gmail_mailboxes(db)
        results: list[dict[str, Any]] = []
        for mailbox in mailboxes:
            try:
                if mailbox.auth_type == "oauth" and mailbox.connection_id:
                    from app.services.communications.gmail_oauth import GmailOAuthService
                    oauth = GmailOAuthService()
                    batch = await oauth.fetch_history(mailbox.connection_id)
                    completed = True
                    cycle_error: str | None = None
                    for entry in batch["entries"]:
                        parsed = self._parse_message(email.message_from_bytes(entry["raw_bytes"]))
                        parsed["_gmail_thread_id"] = entry.get("thread_id")
                        parsed["_gmail_api_message_id"] = entry.get("api_message_id")
                        try:
                            outcome = await self.handle_email(parsed, mailbox=mailbox)
                            results.append(outcome)
                            await oauth.mark_read(mailbox.connection_id, entry["api_message_id"])
                        except Exception as exc:
                            completed = False
                            cycle_error = str(exc)
                            logger.exception("Gmail OAuth inbound message failed")
                            self._mark_inbound_failed(mailbox, parsed, exc)
                            results.append({
                                "auto_replied": False,
                                "reason": f"error: {exc}",
                                "tenant_id": mailbox.tenant_id,
                            })
                            break
                    if completed:
                        oauth.store_history_id(mailbox.connection_id, batch.get("history_id"))
                    self._update_connection_health(mailbox, cycle_error)
                    continue
                if mailbox.connection_id and mailbox.imap_last_uid is None:
                    watermark = self.current_uid_watermark(mailbox)
                    self._store_uid_watermark(mailbox, watermark)
                    self._update_connection_health(mailbox, None)
                    results.append({
                        "auto_replied": False,
                        "reason": "mailbox_baselined",
                        "tenant_id": mailbox.tenant_id,
                    })
                    continue
                entries = self.fetch_unseen(mailbox)
                for entry in entries:
                    try:
                        outcome = await self.handle_email(entry["message"], mailbox=mailbox)
                        results.append(outcome)
                        self.mark_seen(mailbox, entry["uid"])
                        self._store_uid_watermark(mailbox, int(entry["uid"]))
                    except Exception as exc:
                        logger.exception("Gmail inbound message failed")
                        self._mark_inbound_failed(mailbox, entry["message"], exc)
                        results.append({
                            "auto_replied": False,
                            "reason": f"error: {exc}",
                            "tenant_id": mailbox.tenant_id,
                        })
                        break
                self._update_connection_health(mailbox, None)
            except Exception as exc:
                logger.exception("Gmail mailbox poll failed")
                self._update_connection_health(mailbox, str(exc))
                results.append({
                    "auto_replied": False,
                    "reason": f"mailbox_error: {exc}",
                    "tenant_id": mailbox.tenant_id,
                })
        return results
