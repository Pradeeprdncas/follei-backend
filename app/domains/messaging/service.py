import re
from uuid import UUID
from typing import Any
from loguru import logger

from app.domains.messaging.constants import MessageDirection, Channel
from app.domains.messaging.exceptions import MessageValidationError, MessageNotFoundError, ProviderNotConfigured
from app.domains.messaging.repository import MessagingRepository
from app.domains.messaging.dispatcher import MessageDispatcher
from app.domains.messaging.schemas import MessageSendRequest, MessageResponse, MessageListResponse, HealthResponse, HealthStatus, DeliveryStatusResponse
from app.events import DomainEventPublisher, EVENT_MESSAGE_QUEUED, EVENT_MESSAGE_SENT, EVENT_MESSAGE_FAILED
from app.models.conversations.conversation import Message


class MessagingService:
    def __init__(self, repo: MessagingRepository, dispatcher: MessageDispatcher | None = None):
        self.repo = repo
        self.dispatcher = dispatcher or MessageDispatcher()
        self.publisher = DomainEventPublisher(source="messaging")

    async def send_message(self, request: MessageSendRequest, tenant_id: str | None = None) -> MessageResponse:
        self._validate(request)

        tid = UUID(tenant_id) if tenant_id else UUID(int=0)
        conversation, _ = self.repo.get_or_create_conversation(
            tenant_id=tid,
            channel=request.channel,
            recipient=request.recipient,
        )

        msg = self.repo.create_message(
            tenant_id=tid,
            conversation_id=conversation.id,
            channel=request.channel,
            recipient=request.recipient,
            body=request.body,
            subject=request.subject,
            sender=request.sender_name,
            html_body=request.html_body,
            metadata=request.metadata,
        )

        self.repo.create_delivery_status(
            message_id=msg.id,
            tenant_id=tid,
            provider=request.channel,
            status="queued",
        )

        self.publisher.publish(
            EVENT_MESSAGE_QUEUED,
            tenant_id=tenant_id or "unknown",
            data={"message_id": str(msg.id), "channel": request.channel, "recipient": request.recipient},
        )

        try:
            self.repo.update_delivery_status(msg.id, request.channel, status="processing")

            result = await self.dispatcher.dispatch(
                channel=request.channel,
                recipient=request.recipient,
                body=request.body,
                subject=request.subject,
                html_body=request.html_body,
                sender_name=request.sender_name,
                metadata=request.metadata,
            )

            if result.success:
                self.repo.update_delivery_status(
                    msg.id, request.channel, status="sent",
                    provider_message_id=result.provider_message_id,
                )
                self.publisher.publish(
                    EVENT_MESSAGE_SENT,
                    tenant_id=tenant_id or "unknown",
                    data={"message_id": str(msg.id), "provider_message_id": result.provider_message_id},
                )
            else:
                self.repo.update_delivery_status(
                    msg.id, request.channel, status="failed",
                    error=result.error,
                )
                self.publisher.publish(
                    EVENT_MESSAGE_FAILED,
                    tenant_id=tenant_id or "unknown",
                    data={"message_id": str(msg.id), "error": result.error},
                )
        except ProviderNotConfigured as e:
            self.repo.update_delivery_status(msg.id, request.channel, status="failed", error=str(e))
            self.publisher.publish(
                EVENT_MESSAGE_FAILED,
                tenant_id=tenant_id or "unknown",
                data={"message_id": str(msg.id), "error": str(e)},
            )
        except Exception as e:
            logger.exception(f"Send failed for message {msg.id}")
            self.repo.update_delivery_status(msg.id, request.channel, status="failed", error=str(e)[:2000])
            self.publisher.publish(
                EVENT_MESSAGE_FAILED,
                tenant_id=tenant_id or "unknown",
                data={"message_id": str(msg.id), "error": str(e)[:2000]},
            )

        return self._message_to_response(msg)

    def get_message(self, message_id: str) -> MessageResponse:
        try:
            msg = self.repo.get_message(UUID(message_id))
        except ValueError:
            msg = None
        if not msg:
            raise MessageNotFoundError(message_id)
        return self._message_to_response(msg)

    def list_messages(self, tenant_id: str | None = None, limit: int = 50, offset: int = 0) -> list[MessageResponse]:
        if tenant_id:
            msgs = self.repo.get_messages_by_tenant(UUID(tenant_id), limit=limit, offset=offset)
        else:
            msgs = []
        return [self._message_to_response(m) for m in msgs]

    def get_health(self) -> HealthResponse:
        email_status = self.dispatcher.check_health(Channel.EMAIL)
        whatsapp_status = self.dispatcher.check_health(Channel.WHATSAPP)
        sms_status = self.dispatcher.check_health(Channel.SMS)
        all_ok = all(s == "configured" for s in (email_status, whatsapp_status))
        return HealthResponse(
            status="healthy" if all_ok else "degraded",
            providers=HealthStatus(
                email=email_status,
                whatsapp=whatsapp_status,
                sms=sms_status,
            ),
        )

    def _validate(self, request: MessageSendRequest) -> None:
        if not request.recipient:
            raise MessageValidationError("recipient", "recipient is required")
        if request.channel == Channel.EMAIL:
            if not re.match(r"[^@]+@[^@]+\.[^@]+", request.recipient):
                raise MessageValidationError("recipient", "invalid email format")
            if not request.subject:
                raise MessageValidationError("subject", "subject is required for email")
        elif request.channel == Channel.WHATSAPP:
            cleaned = request.recipient.replace("+", "").replace(" ", "").replace("-", "")
            if not cleaned.isdigit() or len(cleaned) < 7:
                raise MessageValidationError("recipient", "invalid phone number format")
        if not request.body:
            raise MessageValidationError("body", "body is required")
        if len(request.body) > 65536:
            raise MessageValidationError("body", "body exceeds maximum length (65536)")

    @staticmethod
    def _message_to_response(msg: Message) -> MessageResponse:
        meta = dict(msg.metadata_ or {})
        return MessageResponse(
            id=str(msg.id),
            public_id=msg.public_id or "",
            tenant_id=str(msg.tenant_id) if msg.tenant_id else None,
            conversation_id=str(msg.conversation_id) if msg.conversation_id else None,
            channel=msg.channel,
            direction=msg.direction,
            role=msg.role,
            content=msg.content,
            message=msg.message,
            message_type=msg.message_type,
            metadata=meta,
            delivery_status=None,
            created_at=msg.created_at,
        )
