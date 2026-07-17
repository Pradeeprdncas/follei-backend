from uuid import UUID
from sqlalchemy.orm import Session
from app.models.integrations.sms import SmsContact, SmsConversation, SmsMessage


class SmsContactRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, contact: SmsContact) -> SmsContact:
        self.db.add(contact)
        self.db.commit()
        self.db.refresh(contact)
        return contact

    def get_by_id(self, contact_id: UUID | str) -> SmsContact | None:
        if isinstance(contact_id, str):
            contact_id = UUID(contact_id)
        return self.db.query(SmsContact).filter(SmsContact.id == contact_id).first()

    def get_by_phone(self, tenant_id: UUID | str, phone: str) -> SmsContact | None:
        if isinstance(tenant_id, str):
            tenant_id = UUID(tenant_id)
        return self.db.query(SmsContact).filter(
            SmsContact.tenant_id == tenant_id,
            SmsContact.phone_number == phone,
        ).first()

    def list_by_tenant(self, tenant_id: UUID | str, skip: int = 0, limit: int = 50) -> list[SmsContact]:
        if isinstance(tenant_id, str):
            tenant_id = UUID(tenant_id)
        return self.db.query(SmsContact).filter(
            SmsContact.tenant_id == tenant_id
        ).offset(skip).limit(limit).all()


class SmsConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, conv: SmsConversation) -> SmsConversation:
        self.db.add(conv)
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def get_by_id(self, conv_id: UUID | str) -> SmsConversation | None:
        if isinstance(conv_id, str):
            conv_id = UUID(conv_id)
        return self.db.query(SmsConversation).filter(SmsConversation.id == conv_id).first()

    def list_by_contact(self, contact_id: UUID | str, skip: int = 0, limit: int = 50) -> list[SmsConversation]:
        if isinstance(contact_id, str):
            contact_id = UUID(contact_id)
        return self.db.query(SmsConversation).filter(
            SmsConversation.contact_id == contact_id
        ).offset(skip).limit(limit).all()

    def list_by_tenant(self, tenant_id: UUID | str, skip: int = 0, limit: int = 50) -> list[SmsConversation]:
        if isinstance(tenant_id, str):
            tenant_id = UUID(tenant_id)
        return self.db.query(SmsConversation).filter(
            SmsConversation.tenant_id == tenant_id
        ).offset(skip).limit(limit).all()


class SmsMessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, msg: SmsMessage) -> SmsMessage:
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def get_by_id(self, msg_id: UUID | str) -> SmsMessage | None:
        if isinstance(msg_id, str):
            msg_id = UUID(msg_id)
        return self.db.query(SmsMessage).filter(SmsMessage.id == msg_id).first()

    def list_by_conversation(self, conv_id: UUID | str, skip: int = 0, limit: int = 100) -> list[SmsMessage]:
        if isinstance(conv_id, str):
            conv_id = UUID(conv_id)
        return self.db.query(SmsMessage).filter(
            SmsMessage.conversation_id == conv_id
        ).order_by(SmsMessage.created_at.asc()).offset(skip).limit(limit).all()

    def get_by_twilio_sid(self, twilio_sid: str) -> SmsMessage | None:
        return self.db.query(SmsMessage).filter(
            SmsMessage.twilio_message_sid == twilio_sid
        ).first()
