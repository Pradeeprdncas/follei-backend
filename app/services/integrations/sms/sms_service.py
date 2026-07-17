import logging
from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.integrations.sms import SmsConversation, SmsMessage
from app.repositories.integrations.sms_repository import (
    SmsContactRepository,
    SmsConversationRepository,
    SmsMessageRepository,
)
from app.services.integrations.sms.auto_reply_service import SmsAutoReplyService
from app.services.integrations.sms.twilio_client import SmsProviderError, TwilioClient
from app.models.tenancy import Tenant

logger = logging.getLogger(__name__)


class SmsService:
    def __init__(
        self,
        db: Session,
        *,
        twilio_client: TwilioClient | None = None,
        auto_reply_service: SmsAutoReplyService | None = None,
    ) -> None:
        self.db = db
        self.contact_repo = SmsContactRepository(db)
        self.conversation_repo = SmsConversationRepository(db)
        self.message_repo = SmsMessageRepository(db)
        self._twilio_client = twilio_client
        self.auto_reply_service = auto_reply_service or SmsAutoReplyService()

    def _active_tenant(self, tenant_id: str):
        if isinstance(tenant_id, str):
            from uuid import UUID
            tenant_id = UUID(tenant_id)
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        if not tenant.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant is inactive")
        return tenant

    def _client(self) -> TwilioClient:
        if self._twilio_client is None:
            try:
                self._twilio_client = TwilioClient()
            except SmsProviderError as exc:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        return self._twilio_client

    async def send_message(self, tenant_id: str, to_phone: str, body: str) -> SmsMessage:
        self._active_tenant(tenant_id)
        try:
            result = await run_in_threadpool(self._client().send_sms, to_phone, body)
        except SmsProviderError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        contact = self.contact_repo.get_by_phone(tenant_id, result["to"])
        if not contact:
            from app.models.integrations.sms import SmsContact
            contact = SmsContact(tenant_id=tenant_id, phone_number=result["to"])
            contact = self.contact_repo.create(contact)

        conversation = self.conversation_repo.list_by_contact(contact.id)
        conv = conversation[0] if conversation else None
        if not conv:
            from app.models.integrations.sms import SmsConversation
            conv = SmsConversation(tenant_id=tenant_id, contact_id=contact.id)
            conv = self.conversation_repo.create(conv)

        from app.models.integrations.sms import SmsMessage as SmsMessageModel
        message = SmsMessageModel(
            tenant_id=tenant_id,
            conversation_id=conv.id,
            direction="outbound",
            from_phone=result["from"],
            to_phone=result["to"],
            body=body,
            status=result["status"],
            twilio_message_sid=result["sid"],
        )
        message = self.message_repo.create(message)
        return message

    async def receive_webhook(
        self,
        from_phone: str,
        to_phone: str,
        body: str,
        message_sid: str,
    ) -> dict:
        duplicate = self.message_repo.get_by_twilio_sid(message_sid)
        if duplicate is not None:
            return {"duplicate": True, "message_id": str(duplicate.id)}

        contact = self.contact_repo.get_by_phone(to_phone, from_phone)
        if not contact:
            from app.models.integrations.sms import SmsContact
            contact = SmsContact(tenant_id=to_phone, phone_number=from_phone)
            contact = self.contact_repo.create(contact)

        conversation = self.conversation_repo.list_by_contact(contact.id)
        conv = conversation[0] if conversation else None
        if not conv:
            from app.models.integrations.sms import SmsConversation
            conv = SmsConversation(tenant_id=contact.tenant_id, contact_id=contact.id)
            conv = self.conversation_repo.create(conv)

        from app.models.integrations.sms import SmsMessage as SmsMessageModel
        inbound = SmsMessageModel(
            tenant_id=contact.tenant_id,
            conversation_id=conv.id,
            direction="inbound",
            from_phone=from_phone,
            to_phone=to_phone,
            body=body,
            status="received",
            twilio_message_sid=message_sid,
        )
        inbound = self.message_repo.create(inbound)
        return {"message_id": str(inbound.id), "conversation_id": str(conv.id)}
