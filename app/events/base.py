"""Base domain event infrastructure.

All domain events inherit from DomainEvent. Each domain module defines its own
event types and event dataclasses in a domain-specific events.py file.
"""
import uuid
import json
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional


# ── Standardized event type constants ─────────────────────────────────────
# Tenant domain
EVENT_TENANT_CREATED = "tenant.created"
EVENT_TENANT_UPDATED = "tenant.updated"
EVENT_TENANT_DISABLED = "tenant.disabled"

# User domain
EVENT_USER_CREATED = "user.created"
EVENT_USER_UPDATED = "user.updated"
EVENT_USER_DISABLED = "user.disabled"

# Lead domain
EVENT_LEAD_CREATED = "lead.created"
EVENT_LEAD_UPDATED = "lead.updated"
EVENT_LEAD_TEMPERATURE_CHANGED = "lead.temperature.changed"
EVENT_LEAD_SCORE_UPDATED = "lead.score.updated"

# Conversation domain
EVENT_CONVERSATION_CREATED = "conversation.created"
EVENT_CONVERSATION_UPDATED = "conversation.updated"
EVENT_CONVERSATION_CLOSED = "conversation.closed"
EVENT_MESSAGE_ADDED = "conversation.message.added"
EVENT_MESSAGE_DELIVERED = "conversation.message.delivered"
EVENT_ANALYSIS_REQUESTED = "conversation.analysis.requested"
EVENT_ANALYSIS_COMPLETED = "conversation.analysis.completed"

# Interaction domain
EVENT_INTERACTION_CREATED = "interaction.created"
EVENT_INTERACTION_UPDATED = "interaction.updated"
EVENT_INTERACTION_CLOSED = "interaction.closed"
EVENT_INTERACTION_ANALYSIS_REQUESTED = "interaction.analysis.requested"
EVENT_INTERACTION_ANALYSIS_COMPLETED = "interaction.analysis.completed"
EVENT_INTERACTION_TRANSCRIPT_READY = "interaction.transcript.ready"

# Campaign domain
EVENT_CAMPAIGN_CREATED = "campaign.created"
EVENT_CAMPAIGN_UPDATED = "campaign.updated"
EVENT_CAMPAIGN_LAUNCHED = "campaign.launched"
EVENT_CAMPAIGN_MESSAGE_SENT = "campaign.message.sent"
EVENT_CAMPAIGN_MESSAGE_DELIVERED = "campaign.message.delivered"

# Customer domain
EVENT_CUSTOMER_CREATED = "customer.created"
EVENT_CUSTOMER_UPDATED = "customer.updated"
EVENT_CUSTOMER_HEALTH_CHANGED = "customer.health.changed"

# Knowledge domain
EVENT_DOCUMENT_UPLOADED = "document.uploaded"
EVENT_DOCUMENT_PROCESSED = "document.processed"
EVENT_DOCUMENT_INDEXED = "document.indexed"
EVENT_DOCUMENT_FAILED = "document.failed"
EVENT_CHUNK_EMBEDDED = "chunk.embedded"
EVENT_ENTITY_EXTRACTED = "entity.extracted"

# Agent domain
EVENT_AGENT_CREATED = "agent.created"
EVENT_AGENT_UPDATED = "agent.updated"
EVENT_AGENT_TASK_ASSIGNED = "agent.task.assigned"
EVENT_AGENT_TASK_COMPLETED = "agent.task.completed"

# Integration domain
EVENT_INTEGRATION_CONNECTED = "integration.connected"
EVENT_INTEGRATION_DISCONNECTED = "integration.disconnected"
EVENT_INTEGRATION_ERROR = "integration.error"

# Product domain
EVENT_PRODUCT_CREATED = "product.created"
EVENT_PRODUCT_UPDATED = "product.updated"

# Messaging domain
EVENT_MESSAGE_QUEUED = "message.queued"
EVENT_MESSAGE_SENT = "message.sent"
EVENT_MESSAGE_DELIVERED = "message.delivered"
EVENT_MESSAGE_FAILED = "message.failed"
EVENT_MESSAGE_READ = "message.read"
EVENT_MESSAGE_CLICKED = "message.clicked"
EVENT_MESSAGE_BOUNCED = "message.bounced"
EVENT_MESSAGE_REPLIED = "message.replied"
EVENT_MESSAGE_COMPLAINED = "message.complained"
EVENT_MESSAGE_UNSUBSCRIBED = "message.unsubscribed"

# Campaign extended events
EVENT_CAMPAIGN_SCHEDULED = "campaign.scheduled"
EVENT_CAMPAIGN_STARTED = "campaign.started"
EVENT_CAMPAIGN_PAUSED = "campaign.paused"
EVENT_CAMPAIGN_COMPLETED = "campaign.completed"
EVENT_CAMPAIGN_CANCELLED = "campaign.cancelled"
EVENT_CAMPAIGN_FAILED = "campaign.failed"

# Billing domain
EVENT_SUBSCRIPTION_CREATED = "subscription.created"
EVENT_SUBSCRIPTION_UPDATED = "subscription.updated"
EVENT_INVOICE_GENERATED = "invoice.generated"
EVENT_PAYMENT_RECEIVED = "payment.received"
EVENT_PAYMENT_FAILED = "payment.failed"


@dataclass
class DomainEvent:
    """Base domain event — all domain events inherit from this."""
    event_id: str
    event_type: str
    source: str
    tenant_id: str
    timestamp: str
    data: dict
    metadata: dict = field(default_factory=lambda: {"version": 1})

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    def to_kafka_message(self) -> tuple[Optional[str], str]:
        return (self.event_type, self.to_json())
