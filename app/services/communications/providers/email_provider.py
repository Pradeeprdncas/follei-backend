"""Email provider — implements CommunicationProvider protocol via Brevo."""
from loguru import logger

from app.services.communications.protocols import CommunicationProvider, SendResult, ProviderHealth
from app.services.communications.email_provider import EmailProvider as _EmailProvider
from app.config.settings import get_settings


class EmailProvider(CommunicationProvider):
    def __init__(self):
        self._inner = _EmailProvider()
        self._settings = get_settings()

    async def send(self, recipient: str, subject: str | None = None,
                   body: str = "", html_body: str | None = None,
                   sender_name: str | None = None,
                   metadata: dict | None = None) -> SendResult:
        metadata = metadata or {}
        attachments = []
        for item in metadata.get("attachments") or []:
            if isinstance(item, dict) and item.get("content_bytes") and item.get("name"):
                attachments.append(item)
        asset_ids = [str(value) for value in metadata.get("asset_ids") or []]
        if asset_ids:
            from uuid import UUID
            from app.database.session import SessionLocal
            from app.models.flows import CommunicationAsset
            from app.services.knowledge.object_storage import read_object
            with SessionLocal() as db:
                for asset_id in asset_ids:
                    try:
                        asset = db.query(CommunicationAsset).filter_by(
                            id=UUID(asset_id), tenant_id=UUID(str(metadata.get("tenant_id"))), status="ready"
                        ).first()
                        if asset:
                            attachments.append({"name": asset.filename, "content_bytes": read_object(asset.object_key), "content_type": asset.content_type})
                    except Exception as exc:
                        logger.warning("Unable to attach communication asset {}: {}", asset_id, exc)
        result = await self._inner.send_email(
            to_email=recipient,
            to_name=metadata.get("to_name", recipient.split("@")[0]),
            subject=subject or "",
            body=body,
            html_body=html_body or body,
            reply_to=metadata.get("reply_to"),
            tenant_id=metadata.get("tenant_id"),
            attachments=attachments or None,
            message_headers=metadata.get("headers"),
        )
        if result.get("success"):
            return SendResult(
                success=True,
                provider_message_id=result.get("message_id"),
                status=result.get("status", "sent"),
                raw_response=result,
            )
        return SendResult(
            success=False,
            error=result.get("error", "Unknown email error"),
            raw_response=result,
        )

    async def send_batch(self, recipients: list[dict], subject: str | None = None,
                         body: str = "", html_body: str | None = None,
                         sender_name: str | None = None) -> list[SendResult]:
        formatted = []
        for r in recipients:
            formatted.append({
                "email": r.get("recipient"),
                "name": r.get("name", r.get("recipient", "").split("@")[0]),
                **(r.get("metadata", {})),
            })
        result = await self._inner.send_bulk_email(
            recipients=formatted,
            subject=subject or "",
            body=body,
            html_body=html_body or body,
        )
        if result.get("success"):
            return [
                SendResult(success=True, provider_message_id=sub.get("message_id"))
                for sub in result.get("results", [])
            ]
        return [SendResult(success=False, error=result.get("error"))]

    async def validate(self, recipient: str) -> bool:
        import re
        return bool(re.match(r"[^@]+@[^@]+\.[^@]+", recipient))

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=bool(self._settings.BREVO_API_KEY),
            message="Brevo configured" if self._settings.BREVO_API_KEY else "BREVO_API_KEY missing",
        )

    def supports_tracking(self) -> bool:
        return True

    def supports_templates(self) -> bool:
        return False

    def supports_attachments(self) -> bool:
        return True

    async def estimate_cost(self, recipient: str, body: str) -> int:
        return 0

    def get_provider_name(self) -> str:
        return "brevo"

    def get_channel(self) -> str:
        return "email"

    def is_configured(self) -> bool:
        return bool(self._settings.BREVO_API_KEY)

    def is_configured_for(self, tenant_id: str | None) -> bool:
        if self.is_configured():
            return True
        if not tenant_id:
            return False
        from app.database.session import SessionLocal
        from app.services.communications.email_connections import brevo_account, has_gmail_oauth_sender
        with SessionLocal() as db:
            return has_gmail_oauth_sender(db, tenant_id) or brevo_account(db, tenant_id) is not None
