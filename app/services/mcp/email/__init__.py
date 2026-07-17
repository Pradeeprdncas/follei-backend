"""Unified email send wrappers — delegates to Gmail, Outlook, or Brevo MCP services."""
from typing import Any, Dict, Optional


async def gmail_send(
    to: str,
    subject: str,
    body: str,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Send email via Gmail MCP service."""
    from app.services.mcp.gmail.auth import GmailAuth
    from app.services.mcp.gmail.service import GmailService

    auth = GmailAuth()
    svc = GmailService(auth)
    result = await svc.send_email(to=to, subject=subject, body=body, cc=cc, bcc=bcc)
    return {"status": "sent", "provider": "gmail", "message_id": result.get("id")}


async def outlook_send(
    to: str,
    subject: str,
    body: str,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Send email via Outlook MCP service."""
    from app.services.mcp.outlook.auth import OutlookAuth
    from app.services.mcp.outlook.service import OutlookService

    auth = OutlookAuth()
    svc = OutlookService(auth)
    result = await svc.send_email(to=to, subject=subject, body=body, cc=cc, bcc=bcc)
    return {"status": "sent", "provider": "outlook", "message_id": result.get("messageId")}


async def brevo_send(
    to: str,
    subject: str,
    body: str,
) -> Dict[str, Any]:
    """Send email via Brevo (Sendinblue) transactional API."""
    import os
    import httpx

    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        return {"status": "error", "detail": "BREVO_API_KEY not configured"}

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "sender": {"email": os.getenv("BREVO_SENDER_EMAIL", "noreply@follei.ai")},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code not in (200, 201):
        return {"status": "error", "detail": f"Brevo API error ({response.status_code}): {response.text}"}

    data = response.json()
    return {"status": "sent", "provider": "brevo", "message_id": data.get("messageId")}
