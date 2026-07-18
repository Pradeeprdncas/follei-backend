"""Canonical SQLAlchemy model registry.

Importing this module registers the UUID operational/knowledge mappings before
any query is executed, preventing relationship names from resolving to a stale
legacy model.
"""
from app.models.tenancy import Tenant, User
from app.models.agents.agent import Agent
from app.models.conversations.conversation import Conversation, Message, ConversationCitation
from app.models.conversations.interaction import Interaction
from app.models.customers.customer import Customer
from app.models.integrations.integration import IntegrationConnection
from app.models.leads.lead import Lead
from app.models.campaigns import Campaign
from app.models.knowledge.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.models.knowledge.entity import Entity, EntityRelation
from app.models.knowledge.sync_event import KnowledgeSyncEvent
from app.models.domain import FAQ, Policy, Procedure, Product, Service, PricingModel, Competitor
from app.models.onboarding_profile import OnboardingProfile
from app.models.onboarding_contact_channel import OnboardingContactChannel
from app.models.onboarding_goal import OnboardingGoal

__all__ = ["Tenant", "User", "Agent", "Conversation", "Message", "ConversationCitation", "Interaction", "Customer", "IntegrationConnection", "Lead", "Campaign", "KnowledgeBase", "Document", "Chunk", "BusinessFactDraft", "Entity", "EntityRelation", "KnowledgeSyncEvent", "OnboardingProfile", "OnboardingContactChannel", "OnboardingGoal"]



