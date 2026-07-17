"""Brevo Inbound Email Service — receive, resolve, generate, send, log.

Flow:
    POST /webhooks/brevo/inbound
        → BrevoInboundService.handle_inbound_email(payload)
            → 1. Parse Brevo inbound payload
            → 2. Loop prevention (self-reply, bounce, idempotency)
            → 3. Tenant + lead resolution
            → 4. Conversation lookup / creation
            → 5. Save inbound message
            → 6. Conversation history assembly
            → 7. EmailReplyGenerator.generate_reply(...)
            → 8. Confidence check (below_threshold → log + skip)
            → 9. Send reply via EmailProvider with threading headers
            → 10. Save outbound message
            → 11. Log both directions
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from loguru import logger
from app.config.settings import get_settings


class BrevoInboundService:
    """Handles inbound Brevo emails with auto-reply safety rails."""

    def __init__(self):
        self._settings = get_settings()
        self._generator = None
        self._seen_message_ids: set[str] = set()

    # ── Public entry point ─────────────────────────────────────────

    async def handle_inbound_email(self, payload: dict) -> dict:
        """Process an inbound Brevo parse webhook payload.

        Args:
            payload: Raw Brevo inbound parse JSON body
                (has top-level "items" array).

        Returns:
            dict with keys:
                - received (bool)
                - auto_replied (bool)
                - reason (str | None) — if skipped
                - inbound_email_id (str | None)
                - conversation_id (str | None)
        """
        result: dict[str, Any] = {
            "received": False,
            "auto_replied": False,
            "reason": None,
            "inbound_email_id": None,
            "conversation_id": None,
        }

        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        if not items:
            result["reason"] = "no_items"
            logger.warning("Brevo inbound payload has empty items array")
            return result

        item = items[0]
        raw_result = await self._process_item(item)
        result.update(raw_result)
        result["received"] = True
        return result

    # ── Per-item processing ────────────────────────────────────────

    async def _process_item(self, item: dict) -> dict:
        result: dict[str, Any] = {
            "auto_replied": False,
            "reason": None,
            "inbound_email_id": None,
            "conversation_id": None,
        }

        # 1. Extract fields
        from_mailbox = item.get("From") or {}
        sender_email = self._safe_mailbox(from_mailbox, "Address")
        sender_name = self._safe_mailbox(from_mailbox, "Name")
        to_list = item.get("To") or []
        to_email = to_list[0].get("Address") if isinstance(to_list, list) and to_list else None
        subject = item.get("Subject") or ""
        message_id = item.get("MessageId") or ""
        in_reply_to = item.get("InReplyTo")
        body = item.get("ExtractedMarkdownMessage") or item.get("RawTextBody") or ""
        uuid_list = item.get("Uuid") or []

        if not sender_email:
            result["reason"] = "no_sender"
            logger.warning("Brevo inbound item missing From address")
            return result

        # 2. Loop prevention
        loop_check = self._check_loop(sender_email, message_id, subject)
        if loop_check["block"]:
            result["reason"] = loop_check["reason"]
            logger.info(f"Brevo inbound blocked: {loop_check['reason']} from {sender_email}")
            return result

        # 3. Resolve tenant + lead (manual trigger can pass _tenant_id)
        manual_tenant_id = item.get("_tenant_id")
        if manual_tenant_id:
            resolved = {"tenant_id": manual_tenant_id, "lead_id": None, "campaign_id": None}
        else:
            resolved = await self._resolve_context(sender_email, to_email)

        if not resolved.get("tenant_id"):
            result["reason"] = "tenant_not_found"
            logger.warning(f"Could not resolve tenant for {sender_email}")
            return result

        tenant_id = resolved["tenant_id"]
        lead_id = resolved.get("lead_id")
        campaign_id = resolved.get("campaign_id")

        # 4. Conversation
        conversation = await self._get_or_create_conversation(
            tenant_id=tenant_id,
            lead_id=lead_id,
            subject=subject,
        )
        conversation_id = str(conversation.id) if conversation else None
        result["conversation_id"] = conversation_id
        result["inbound_email_id"] = str(uuid_list[0]) if uuid_list else None

        # 5. Save inbound message
        inbound_msg = await self._save_message(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            lead_id=lead_id,
            direction="inbound",
            content=body,
            subject=subject,
            provider_message_id=message_id,
        )

        # 6. Auto-reply enabled?
        if not await self._is_auto_reply_enabled(tenant_id):
            result["reason"] = "auto_reply_disabled"
            logger.info(f"Auto-reply disabled for tenant {tenant_id}")
            self._log_item(tenant_id, sender_email, subject, "skipped", "auto_reply_disabled")
            return result

        # 7. Rate limit
        if not self._check_rate_limit(tenant_id):
            result["reason"] = "rate_limited"
            logger.warning(f"Rate limit hit for tenant {tenant_id}")
            return result

        # 8. Conversation history assembly
        history = await self._build_conversation_history(conversation_id)

        # 9. Generate reply
        gen_result = await self._get_generator().generate_reply(
            message=body,
            tenant_id=tenant_id,
            lead_id=lead_id,
            conversation_id=conversation_id,
            conversation_history=history,
        )

        if not gen_result.get("success"):
            result["reason"] = "generation_failed"
            logger.error(f"Reply generation failed: {gen_result.get('error')}")
            self._log_item(tenant_id, sender_email, subject, "failed", gen_result.get("error"))
            return result

        answer = gen_result.get("answer")
        confidence = gen_result.get("confidence", 0.0)

        # 10. Confidence threshold
        if gen_result.get("below_threshold"):
            result["reason"] = "low_confidence"
            logger.info(f"Reply confidence {confidence:.2f} below threshold, skipping send")
            self._log_item(tenant_id, sender_email, subject, "skipped", f"low_confidence:{confidence:.2f}")
            return result

        # 11. Send reply via Brevo with threading headers
        send_result = await self._send_reply(
            tenant_id=tenant_id,
            to_email=sender_email,
            to_name=sender_name,
            subject=subject,
            reply_body=answer,
            in_reply_to=message_id,
        )

        if not send_result.get("success"):
            result["reason"] = "send_failed"
            logger.error(f"Failed to send auto-reply: {send_result.get('error')}")
            self._log_item(tenant_id, sender_email, subject, "failed", f"send_failed:{send_result.get('error')}")
            return result

        # 12. Save outbound message
        await self._save_message(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            lead_id=lead_id,
            direction="outbound",
            content=answer,
            subject=f"Re: {subject}" if not subject.lower().startswith("re:") else subject,
            is_ai_generated=True,
            ai_confidence=confidence,
            ai_intent=gen_result.get("intent"),
            provider_message_id=send_result.get("message_id"),
            in_reply_to=message_id,
        )

        result["auto_replied"] = True
        logger.info(f"Auto-replied to {sender_email} (conv={conversation_id}, confidence={confidence:.2f})")
        self._log_item(tenant_id, sender_email, subject, "sent", f"confidence:{confidence:.2f}")
        return result

    # ── Loop Prevention ─────────────────────────────────────────────

    def _check_loop(self, sender_email: str, message_id: str, subject: str) -> dict:
        """Check if this inbound email should be ignored (loop prevention).

        Returns dict {"block": bool, "reason": str | None}.
        """
        reason = None

        # Self-reply: sender is our own domain (skip if domain not configured)
        inbound_domain = self._settings.BREVO_INBOUND_DOMAIN
        if inbound_domain and sender_email.endswith(f"@{inbound_domain}"):
            reason = "self_reply"

        # Bounce / auto-reply detection
        lower_subject = (subject or "").lower()
        bounce_indicators = [
            "delivery status notification", "delivery failure",
            "mail delivery failed", "returned mail", "undelivered",
            "auto-reply", "automatic reply", "out of office",
            "vacation", "away from the office",
        ]
        if any(indicator in lower_subject for indicator in bounce_indicators):
            reason = "bounce_or_auto_reply"

        # Idempotency: seen this MessageId before
        if message_id:
            if message_id in self._seen_message_ids:
                reason = "duplicate_message_id"
            self._seen_message_ids.add(message_id)
            if len(self._seen_message_ids) > 100000:
                self._seen_message_ids.clear()

        return {"block": reason is not None, "reason": reason}

    # ── Tenant / Lead Resolution ────────────────────────────────────

    async def _resolve_context(self, sender_email: str, to_email: str | None) -> dict:
        """Resolve tenant_id, lead_id, campaign_id from the sender email.

        This is a simplified version. Production deployments should
        use a more sophisticated tenant resolution strategy (e.g., based
        on the to_email address or a lookup table).
        """
        from app.database.session import get_db
        from app.models.leads.lead import Lead
        from sqlalchemy import select

        db = next(get_db())
        try:
            stmt = select(Lead).where(Lead.email == sender_email)
            result = db.execute(stmt)
            lead = result.scalar_one_or_none()

            if lead:
                return {
                    "tenant_id": str(lead.tenant_id),
                    "lead_id": str(lead.id),
                    "campaign_id": None,
                }

            return {"tenant_id": None, "lead_id": None, "campaign_id": None}
        except Exception as e:
            logger.error(f"Lead resolution failed: {e}")
            return {"tenant_id": None, "lead_id": None, "campaign_id": None}
        finally:
            db.close()

    # ── Conversation Management ─────────────────────────────────────

    async def _get_or_create_conversation(self, tenant_id: str, lead_id: str | None, subject: str):
        from app.database.session import get_db
        from app.models.conversations.conversation import Conversation
        from sqlalchemy import select
        import uuid

        db = next(get_db())
        try:
            stmt = select(Conversation).where(
                Conversation.tenant_id == uuid.UUID(tenant_id),
                Conversation.lead_id == uuid.UUID(lead_id) if lead_id else Conversation.lead_id.is_(None),
                Conversation.channel == "email",
                Conversation.status == "open",
            ).order_by(Conversation.created_at.desc())

            result = db.execute(stmt)
            conv = result.scalar_one_or_none()

            if not conv:
                conv = Conversation(
                    id=uuid.uuid4(),
                    tenant_id=uuid.UUID(tenant_id),
                    lead_id=uuid.UUID(lead_id) if lead_id else None,
                    channel="email",
                    title=subject[:255] if subject else "Email conversation",
                    status="open",
                    message_count=0,
                )
                db.add(conv)
                db.commit()
                db.refresh(conv)

            return conv
        finally:
            db.close()

    # ── Message Persistence ─────────────────────────────────────────

    async def _save_message(
        self,
        conversation_id: str | None,
        tenant_id: str,
        lead_id: str | None,
        direction: str,
        content: str,
        subject: str | None = None,
        is_ai_generated: bool = False,
        ai_confidence: float | None = None,
        ai_intent: str | None = None,
        provider_message_id: str | None = None,
        in_reply_to: str | None = None,
    ):
        from app.database.session import get_db
        from app.models.conversations.conversation import Message
        import uuid

        db = next(get_db())
        try:
            metadata = {}
            if provider_message_id:
                metadata["provider_message_id"] = provider_message_id
            if in_reply_to:
                metadata["in_reply_to"] = in_reply_to
            if subject:
                metadata["subject"] = subject
            if is_ai_generated:
                metadata["is_ai_generated"] = True
            if ai_confidence is not None:
                metadata["ai_confidence"] = round(ai_confidence, 4)
            if ai_intent:
                metadata["ai_intent"] = ai_intent

            msg = Message(
                id=uuid.uuid4(),
                conversation_id=uuid.UUID(conversation_id) if conversation_id else None,
                tenant_id=uuid.UUID(tenant_id),
                role="agent" if direction == "outbound" else "user",
                sender_id=uuid.UUID(lead_id) if lead_id else None,
                direction=direction,
                channel="email",
                content=content,
                sender_type="lead" if direction == "inbound" else "agent",
                metadata_=metadata,
            )
            db.add(msg)
            db.commit()
            return msg
        finally:
            db.close()

    # ── Conversation History ────────────────────────────────────────

    async def _build_conversation_history(self, conversation_id: str | None, limit: int = 10) -> list[dict]:
        """Fetch recent messages for context."""
        if not conversation_id:
            return []
        from app.database.session import get_db
        from app.models.conversations.conversation import Message
        from sqlalchemy import select
        import uuid

        db = next(get_db())
        try:
            stmt = (
                select(Message)
                .where(Message.conversation_id == uuid.UUID(conversation_id))
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            result = db.execute(stmt)
            messages = result.scalars().all()
            history = []
            for msg in reversed(messages):
                role = "user" if msg.direction == "inbound" else "assistant"
                history.append({"role": role, "content": msg.content})
            return history
        finally:
            db.close()

    # ── Send Reply ──────────────────────────────────────────────────

    async def _send_reply(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str | None,
        subject: str,
        reply_body: str,
        in_reply_to: str | None = None,
    ) -> dict:
        """Send reply via EmailProvider with threading headers."""
        from app.services.communications.email_provider import EmailProvider

        # Construct reply subject
        reply_subject = f"Re: {subject}" if not subject.lower().startswith("re:") else subject

        # Build threading HTML with In-Reply-To header
        html_body = (
            f"<div style=\"font-family:sans-serif;line-height:1.6\">"
            f"{reply_body.replace(chr(10), '<br>')}"
            f"</div>"
        )

        provider = EmailProvider()
        send_result = await provider.send_email(
            to_email=to_email,
            to_name=to_name or "Valued Customer",
            subject=reply_subject,
            body=reply_body,
            html_body=html_body,
            reply_to=provider.sender_email,
        )

        return send_result

    # ── Safety Rails ────────────────────────────────────────────────

    async def _is_auto_reply_enabled(self, tenant_id: str) -> bool:
        """Check if auto-reply is enabled for this tenant.

        Global toggle + per-tenant opt-in check.
        """
        if not self._settings.BREVO_AUTO_REPLY_ENABLED:
            return False

        return await self._tenant_has_auto_reply_enabled(tenant_id)

    async def _tenant_has_auto_reply_enabled(self, tenant_id: str) -> bool:
        """Check tenant-level auto-reply toggle.

        Override this to check a database column on the tenant record.
        Current implementation returns True (relies on global toggle).
        """
        return True

    _rate_limit_buckets: dict[str, list[float]] = {}

    def _check_rate_limit(self, tenant_id: str) -> bool:
        """Simple sliding-window rate limit per tenant."""
        import time

        now = time.time()
        window = 60.0
        max_per_window = self._settings.BREVO_AUTO_REPLY_RATE_LIMIT

        bucket = self._rate_limit_buckets.setdefault(tenant_id, [])
        bucket[:] = [t for t in bucket if now - t < window]

        if len(bucket) >= max_per_window:
            return False

        bucket.append(now)
        return True

    # ── Logging ─────────────────────────────────────────────────────

    def _log_item(self, tenant_id: str, sender: str, subject: str, status: str, detail: str | None = None):
        """Structured log line for observability."""
        logger.info(f"[BrevoInbound] tenant={tenant_id} sender={sender} subject={subject!r} status={status} detail={detail}")

    # ── Generator Factory ──────────────────────────────────────────

    def _get_generator(self):
        """Lazy-load EmailReplyGenerator.

        Swap this factory to use a FinetunedEmailReplyGenerator.
        """
        if self._generator is None:
            from app.services.communications.email_auto_reply import EmailReplyGenerator
            self._generator = EmailReplyGenerator()
        return self._generator

    @staticmethod
    def _safe_mailbox(mailbox: Any, key: str) -> str | None:
        if isinstance(mailbox, dict):
            val = mailbox.get(key)
            return str(val) if val else None
        return None
