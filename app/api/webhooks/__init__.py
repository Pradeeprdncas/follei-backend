"""Webhook endpoints for third-party integrations (Brevo inbound parse, etc.)."""
from fastapi import APIRouter, HTTPException, Request, Body
from pydantic import BaseModel
from loguru import logger
from typing import Optional

from app.services.communications.webhooks import WebhookValidator, ReplayProtection
from app.services.communications.brevo_inbound import BrevoInboundService

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
_validator = WebhookValidator()
_replay = ReplayProtection()


# ── Schemas ────────────────────────────────────────────────────────

class ManualAutoReplyRequest(BaseModel):
    from_email: str
    subject: str = ""
    body: str
    tenant_id: Optional[str] = None


# ── Brevo Inbound Parse Webhook ────────────────────────────────────

@router.post("/brevo/inbound")
async def brevo_inbound_webhook(request: Request):
    """Receive inbound email parse events from Brevo.

    Brevo sends parsed email payloads as POST to this endpoint.
    The payload has a top-level "items" array.

    Optional HMAC signature validation via X-Brevo-Signature header.
    """
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Brevo webhook: invalid JSON body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    # Optional signature validation
    signature = request.headers.get("X-Brevo-Signature")
    timestamp = request.headers.get("X-Brevo-Timestamp")
    if signature:
        if not _validator.validate_brevo(body, signature, timestamp):
            logger.warning("Brevo webhook signature validation failed")
            raise HTTPException(status_code=401, detail="Invalid signature")
        if not _replay.check_timestamp(timestamp):
            logger.warning("Brevo webhook replay check failed")
            raise HTTPException(status_code=401, detail="Replay detected")

    service = BrevoInboundService()
    result = await service.handle_inbound_email(body)

    status_code = 200 if result.get("received") else 400
    return result


# ── Manual Trigger (no Brevo domain / DNS needed) ──────────────────

@router.post("/email/auto-reply")
async def manual_auto_reply(payload: ManualAutoReplyRequest):
    """Trigger auto-reply manually — no Brevo inbound domain needed.

    Use this endpoint to test or trigger auto-replies via curl/API
    without setting up DNS MX records for Brevo inbound parsing.

    Body:
        from_email: sender's email address
        subject: email subject line
        body: email body text
        tenant_id: optional (auto-resolved from lead if omitted)

    Returns the same result as the Brevo webhook handler.
    """
    if not payload.from_email:
        raise HTTPException(status_code=400, detail="from_email is required")

    brevo_payload = {
        "items": [{
            "From": {"Address": payload.from_email, "Name": None},
            "To": [{"Address": None, "Name": None}],
            "Subject": payload.subject,
            "ExtractedMarkdownMessage": payload.body,
            "RawTextBody": payload.body,
            "MessageId": None,
            "InReplyTo": None,
            "Uuid": [],
        }]
    }

    if payload.tenant_id:
        brevo_payload["items"][0]["_tenant_id"] = payload.tenant_id

    service = BrevoInboundService()
    result = await service.handle_inbound_email(brevo_payload)

    status_code = 200 if result.get("received") else 400
    return result
