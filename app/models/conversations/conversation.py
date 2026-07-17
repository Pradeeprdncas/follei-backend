import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.core.public_id import generate_public_id


class Conversation(Base):
    """
    Represents a chat thread between an end-user/lead and an AI Agent.
    """
    __tablename__ = "conversations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    customer_id = Column(Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    lead_id = Column(Uuid(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    public_id = Column(String, unique=True, index=True, nullable=True)
    
    title = Column(String, nullable=True)
    channel = Column(String, nullable=True)
    status = Column(String, default="open", nullable=False)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)

    # Analysis tracking
    summary = Column(Text, nullable=True)
    analysis_status = Column(String, default="pending", nullable=False)
    last_analysis_at = Column(DateTime, nullable=True)
    current_lead_temperature = Column(String, nullable=True)
    message_count = Column(Integer, default=0, nullable=False)
    last_activity_at = Column(DateTime, nullable=True)
    last_message_at = Column(DateTime, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="conversations")
    agent = relationship("Agent", back_populates="conversations")
    customer = relationship("Customer", back_populates="conversations")
    lead = relationship("Lead", back_populates="conversations")
    interactions = relationship("Interaction", back_populates="conversation", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    agent_sessions = relationship("AgentSession", back_populates="conversation")
    actions = relationship("ConversationAction", back_populates="conversation", cascade="all, delete-orphan")
    analytics = relationship("ConversationAnalytics", back_populates="conversation")
    buying_signals = relationship("ConversationBuyingSignal", back_populates="conversation")
    emotions = relationship("ConversationEmotion", back_populates="conversation")
    entities = relationship("ConversationEntity", back_populates="conversation")
    feedback = relationship("ConversationFeedback", back_populates="conversation")
    intents = relationship("ConversationIntent", back_populates="conversation")
    metrics = relationship("ConversationMetric", back_populates="conversation")
    objections = relationship("ConversationObjection", back_populates="conversation")
    participants = relationship("ConversationParticipant", back_populates="conversation")
    sentiments = relationship("ConversationSentiment", back_populates="conversation")
    summaries = relationship("ConversationSummary", back_populates="conversation")
    transcripts = relationship("ConversationTranscript", back_populates="conversation")
    call_sessions = relationship("CallSession", back_populates="conversation", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("Conversation")


class Message(Base):
    __tablename__ = "conversation_messages"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    interaction_id = Column(Uuid(as_uuid=True), ForeignKey("interactions.id", ondelete="SET NULL"), nullable=True, index=True)
    public_id = Column(String, unique=True, index=True, nullable=True)
    
    role = Column(String, nullable=False) # 'user', 'agent', 'system', 'tool'
    content = Column(Text, nullable=False)
    sender_type = Column(String, nullable=True)
    sender_id = Column(Uuid(as_uuid=True), nullable=True)
    message = Column(Text, nullable=True)
    message_type = Column(String, default="text", nullable=False)

    # Multi-channel message fields
    sequence_number = Column(Integer, nullable=True)
    direction = Column(String, nullable=True)  # 'inbound', 'outbound'
    speaker = Column(String, nullable=True)  # lead, agent, system, bot
    channel = Column(String, nullable=True)  # whatsapp, sms, email, chat, call, instagram, web

    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    idempotency_key = Column(String(160), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="messages")
    conversation = relationship("Conversation", back_populates="messages")
    interaction = relationship("Interaction", back_populates="messages")
    agent_confidence_scores = relationship("AgentConfidenceScore", back_populates="message")
    agent_feedback = relationship("AgentFeedback", back_populates="message")
    attachments = relationship("MessageAttachment", back_populates="message", cascade="all, delete-orphan")
    chunk_citations = relationship("ChunkCitation", back_populates="message")
    conversation_citations = relationship("ConversationCitation", back_populates="message", cascade="all, delete-orphan")
    delivery_statuses = relationship("MessageDeliveryStatus", back_populates="message", cascade="all, delete-orphan")
    emotions = relationship("ConversationEmotion", back_populates="message")
    feedback = relationship("ConversationFeedback", back_populates="message")
    reactions = relationship("MessageReaction", back_populates="message", cascade="all, delete-orphan")
    response_metrics = relationship("ResponseMetric", back_populates="message")
    sentiments = relationship("ConversationSentiment", back_populates="message")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = generate_public_id("Message")


class ConversationAction(Base):
    __tablename__ = "conversation_actions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String, nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    status = Column(String, default="completed", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="actions")
    agent = relationship("Agent")


class ConversationAnalytics(Base):
    __tablename__ = "conversation_analytics"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True)
    metrics = Column(JSON, default=dict, nullable=False)
    measured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="analytics")


class ConversationBuyingSignal(Base):
    __tablename__ = "conversation_buying_signals"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    signal_type = Column(String, nullable=False)
    evidence = Column(Text, nullable=True)
    confidence = Column(Numeric, nullable=True)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="buying_signals")


class ConversationCitation(Base):
    __tablename__ = "conversation_citations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    chunk_id = Column(Uuid(as_uuid=True), ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True)
    quote = Column(Text, nullable=True)
    confidence = Column(Numeric, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    message = relationship("Message", back_populates="conversation_citations")
    document = relationship("Document", back_populates="conversation_citations")
    chunk = relationship("DocumentChunk", back_populates="conversation_citations")


class ConversationEmotion(Base):
    __tablename__ = "conversation_emotions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="CASCADE"), nullable=True)
    emotion = Column(String, nullable=False)
    score = Column(Numeric, nullable=True)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="emotions")
    message = relationship("Message", back_populates="emotions")


class ConversationEntity(Base):
    __tablename__ = "conversation_entities"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Uuid(as_uuid=True), nullable=True)
    entity_text = Column(String, nullable=True)
    entity_type = Column(String, nullable=True)
    confidence = Column(Numeric, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="entities")


class ConversationFeedback(Base):
    __tablename__ = "conversation_feedback"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="SET NULL"), nullable=True)
    rating = Column(Integer, nullable=True)
    feedback = Column(Text, nullable=True)
    feedback_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="feedback")
    message = relationship("Message", back_populates="feedback")


class ConversationIntent(Base):
    __tablename__ = "conversation_intents"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    intent = Column(String, nullable=False)
    confidence = Column(Numeric, nullable=True)
    evidence = Column(Text, nullable=True)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="intents")


class ConversationMetric(Base):
    __tablename__ = "conversation_metrics"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    response_time_seconds = Column(Numeric, nullable=True)
    resolution_time_seconds = Column(Numeric, nullable=True)
    message_count = Column(Integer, default=0, nullable=False)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="metrics")


class ConversationObjection(Base):
    __tablename__ = "conversation_objections"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    objection_type = Column(String, nullable=False)
    evidence = Column(Text, nullable=True)
    confidence = Column(Numeric, nullable=True)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="objections")


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    participant_type = Column(String, nullable=False)
    participant_id = Column(Uuid(as_uuid=True), nullable=True)
    display_name = Column(String, nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    left_at = Column(DateTime, nullable=True)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="participants")


class ConversationSentiment(Base):
    __tablename__ = "conversation_sentiments"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="CASCADE"), nullable=True)
    sentiment = Column(String, nullable=False)
    score = Column(Numeric, nullable=True)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="sentiments")
    message = relationship("Message", back_populates="sentiments")


class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    summary_type = Column(String, default="ai", nullable=False)
    summary = Column(Text, nullable=False)
    source_message_count = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="ready")
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    created_by = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="summaries")
    creator = relationship("User")


class ConversationTranscript(Base):
    __tablename__ = "conversation_transcripts"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    transcript = Column(Text, nullable=False)
    provider = Column(String, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="transcripts")


class MessageAttachment(Base):
    __tablename__ = "message_attachments"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String, nullable=True)
    file_url = Column(Text, nullable=True)
    content_type = Column(String, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    message = relationship("Message", back_populates="attachments")


class MessageDeliveryStatus(Base):
    __tablename__ = "message_delivery_status"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False)
    provider = Column(String, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    message = relationship("Message", back_populates="delivery_statuses")


class MessageReaction(Base):
    __tablename__ = "message_reactions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reaction = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    message = relationship("Message", back_populates="reactions")
    user = relationship("User")


class ResponseMetric(Base):
    __tablename__ = "response_metrics"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="SET NULL"), nullable=True)
    quality_score = Column(Numeric, nullable=True)
    metrics = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    message = relationship("Message", back_populates="response_metrics")


class CallSession(Base):
    """One row per call session with compressed JSONB transcript/sentiment/emotion/timeline."""
    __tablename__ = "call_sessions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    interaction_id = Column(Uuid(as_uuid=True), ForeignKey("interactions.id", ondelete="SET NULL"), nullable=True, index=True)

    # Provider info
    call_sid = Column(String, nullable=True, index=True)
    provider = Column(String, nullable=True)

    # Direction & status
    direction = Column(String, nullable=True)  # inbound, outbound
    status = Column(String, default="pending", nullable=False)  # ringing, in-progress, completed, failed, busy, no-answer

    # Participants
    from_number = Column(String, nullable=True)
    to_number = Column(String, nullable=True)

    # Recording
    recording_url = Column(Text, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # Analysis data (JSONB - compressed, queryable)
    transcript = Column(JSONB, nullable=False, default=dict)
    sentiment = Column(JSONB, nullable=False, default=dict)
    emotion = Column(JSONB, nullable=False, default=dict)
    timeline = Column(JSONB, nullable=False, default=list)  # ordered events during call
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)

    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    conversation = relationship("Conversation", back_populates="call_sessions")
    interaction = relationship("Interaction", back_populates="call_session")



