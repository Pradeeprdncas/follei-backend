import uuid
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.conversations.conversation import Message, Conversation, MessageDeliveryStatus


class MessagingRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_message(self, tenant_id: UUID, conversation_id: UUID, channel: str,
                       recipient: str, body: str, subject: str | None = None,
                       sender: str | None = None, html_body: str | None = None,
                       role: str = "agent", direction: str = "outbound",
                       interaction_id: UUID | None = None,
                       metadata: dict | None = None) -> Message:
        msg_meta = {
            "recipient": recipient,
            "subject": subject or "",
            "html_body": html_body or "",
            "sender": sender or "",
            **(metadata or {}),
        }
        msg = Message(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            interaction_id=interaction_id,
            role=role,
            content=body,
            sender_type=channel,
            message=subject or body[:100],
            message_type="email" if html_body else "text",
            direction=direction,
            channel=channel,
            metadata_=msg_meta,
        )
        self.db.add(msg)
        self.db.flush()
        return msg

    def create_delivery_status(self, message_id: UUID, tenant_id: UUID,
                                provider: str, status: str = "queued") -> MessageDeliveryStatus:
        ds = MessageDeliveryStatus(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            message_id=message_id,
            provider=provider,
            status=status,
            metadata_={},
        )
        self.db.add(ds)
        self.db.flush()
        return ds

    def update_delivery_status(self, message_id: UUID, provider: str, status: str,
                                 provider_message_id: str | None = None,
                                 error: str | None = None) -> MessageDeliveryStatus | None:
        ds = self.db.execute(
            select(MessageDeliveryStatus)
            .where(MessageDeliveryStatus.message_id == message_id)
            .where(MessageDeliveryStatus.provider == provider)
            .order_by(MessageDeliveryStatus.created_at.desc())
        ).scalars().first()
        if not ds:
            return None
        ds.status = status
        if status == "delivered":
            ds.delivered_at = datetime.utcnow()
        meta = dict(ds.metadata_ or {})
        if provider_message_id:
            meta["provider_message_id"] = provider_message_id
        if error:
            meta["error"] = error
        ds.metadata_ = meta
        self.db.flush()
        return ds

    def get_message(self, message_id: UUID) -> Message | None:
        return self.db.get(Message, message_id)

    def get_messages_by_tenant(self, tenant_id: UUID, limit: int = 50, offset: int = 0) -> list[Message]:
        return list(self.db.execute(
            select(Message)
            .where(Message.tenant_id == tenant_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).scalars().all())

    def get_delivery_status(self, message_id: UUID) -> list[MessageDeliveryStatus]:
        return list(self.db.execute(
            select(MessageDeliveryStatus)
            .where(MessageDeliveryStatus.message_id == message_id)
            .order_by(MessageDeliveryStatus.created_at.desc())
        ).scalars().all())

    def get_or_create_conversation(self, tenant_id: UUID, channel: str,
                                    recipient: str) -> tuple[Conversation, bool]:
        conversation = self.db.execute(
            select(Conversation)
            .where(Conversation.tenant_id == tenant_id)
            .where(Conversation.channel == channel)
            .order_by(Conversation.created_at.desc())
        ).scalars().first()
        if conversation:
            return conversation, False
        conversation = Conversation(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            channel=channel,
            title=f"{channel.upper()} - {recipient}",
            status="open",
            metadata_={},
        )
        self.db.add(conversation)
        self.db.flush()
        return conversation, True
