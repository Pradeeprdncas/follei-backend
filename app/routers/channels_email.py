"""Inbound email channel for the Support worker.

Webhook-shaped, not IMAP-polling — this is how real inbound email delivery
works with providers like SendGrid/Brevo/Postmark's inbound parse: the
provider POSTs the parsed message to us. No SMTP/provider credentials are
configured in this environment, so there is no live provider wired up yet;
this endpoint is what a provider would call, and it returns the generated
reply directly (the same content an outbound sender would dispatch) so the
full inbound-to-reply round trip is provable without one.

No JWT here deliberately: an email provider webhook has no interactive user
to hold a bearer token. Protected instead by an optional shared secret
(EMAIL_INBOUND_WEBHOOK_SECRET) checked against X-Webhook-Secret.
"""
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.config.database import SessionLocal
from app.config.settings import get_settings
from app.services.agents.support.worker import handle_inbound_message

router = APIRouter(prefix="/channels/email", tags=["channels-email"])
_settings = get_settings()


class InboundEmailMessage(BaseModel):
    tenant_id: str
    from_address: EmailStr
    subject: str = Field(default="")
    body: str = Field(..., min_length=1)
    thread_id: str | None = Field(default=None, description="Provider's thread/message id, used as the conversation session_id so replies in the same thread resume the same conversation.")


def _check_webhook_secret(secret_header: str | None) -> None:
    if not _settings.EMAIL_INBOUND_WEBHOOK_SECRET:
        return
    if secret_header != _settings.EMAIL_INBOUND_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing webhook secret")


@router.post("/inbound")
async def inbound_email(payload: InboundEmailMessage, x_webhook_secret: str | None = Header(default=None)):
    _check_webhook_secret(x_webhook_secret)
    db = SessionLocal()
    try:
        result = await handle_inbound_message(
            db, tenant_id=payload.tenant_id, text=payload.body,
            session_id=payload.thread_id, channel="email",
        )
    finally:
        db.close()
    return {
        "from": payload.from_address,
        "subject": f"Re: {payload.subject}" if payload.subject else "Re: your message",
        **result,
    }
