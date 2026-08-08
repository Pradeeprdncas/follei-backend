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
from app.models.integrations.email_connection import EmailOAuthState, TenantEmailConnection
from app.models.integrations.channel_connection import ChannelComplianceAcknowledgement, TenantChannelConnection
from app.models.integrations.oauth_connection import IntegrationOAuthState, GoogleWorkspaceConnection
from app.models.leads.lead import Lead
from app.models.campaigns import Campaign
from app.models.knowledge.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.knowledge.fact_draft import BusinessFactDraft
from app.models.knowledge.entity import Entity, EntityRelation
from app.models.knowledge.sync_event import KnowledgeSyncEvent
from app.models.knowledge.indexing_job import IndexingJob
from app.models.knowledge.ingestion import IngestionRun, SourceIngestionJob, CategorySummary, OnboardingConfirmation
from app.models.knowledge.document import KnowledgeSource
from app.models.domain import FAQ, Policy, Procedure, Product, Service, SLA, PricingModel, Competitor, BusinessPlan, CustomerSegment
from app.models.onboarding_profile import OnboardingProfile
from app.models.onboarding_contact_channel import OnboardingContactChannel
from app.models.onboarding_goal import OnboardingGoal
from app.models.learning_signal import LearningSignal
from app.models.flows import FlowDefinition, FlowVersion, FlowEnrollment, FlowExecutionStep, CommunicationAsset, WorkflowTemplate, TenantWorkflowInstance, WorkflowApproval
from app.models.crm import CRMRecord, CRMSyncRun, TenantCRMConnection
from app.domains.lead_import.models import LeadImportJob, LeadImportRow
from app.analysis.models.conversation_analysis import ConversationAnalysis

__all__ = ["Tenant", "User", "Agent", "Conversation", "Message", "ConversationCitation", "Interaction", "Customer", "IntegrationConnection", "EmailOAuthState", "TenantEmailConnection", "IntegrationOAuthState", "GoogleWorkspaceConnection", "TenantChannelConnection", "ChannelComplianceAcknowledgement", "Lead", "Campaign", "KnowledgeBase", "KnowledgeSource", "Document", "Chunk", "BusinessFactDraft", "Entity", "EntityRelation", "KnowledgeSyncEvent", "IndexingJob", "IngestionRun", "SourceIngestionJob", "CategorySummary", "OnboardingConfirmation", "OnboardingProfile", "OnboardingContactChannel", "OnboardingGoal", "BusinessPlan", "CustomerSegment", "SLA", "LearningSignal", "FlowDefinition", "FlowVersion", "FlowEnrollment", "FlowExecutionStep", "CommunicationAsset", "WorkflowTemplate", "TenantWorkflowInstance", "WorkflowApproval", "TenantCRMConnection", "CRMRecord", "CRMSyncRun", "LeadImportJob", "LeadImportRow", "ConversationAnalysis"]
