"""MCP Tools - Expose CRM and communication tools for AI agent."""
from typing import Dict, Any, List, Optional
from loguru import logger
from app.config.settings import get_settings

_settings = get_settings()


class EmailTool:
    """MCP Tool for sending emails."""
    
    name = "send_email"
    description = "Send an email to a lead or customer"
    
    async def execute(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        body: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Send email via Brevo.
        
        Args:
            to_email: Recipient email
            to_name: Recipient name
            subject: Email subject
            body: Email body
            
        Returns:
            Send result
        """
        try:
            from app.services.communications.email_provider import EmailProvider
            provider = EmailProvider()
            result = await provider.send_email(
                to_email=to_email,
                to_name=to_name,
                subject=subject,
                body=body,
            )
            return result
        except Exception as e:
            logger.error(f"EmailTool failed: {e}")
            return {"success": False, "error": str(e)}


class WhatsAppTool:
    """MCP Tool for sending WhatsApp messages."""
    
    name = "send_whatsapp"
    description = "Send a WhatsApp message to a lead or customer"
    
    async def execute(
        self,
        to_phone: str,
        message: str,
        media_url: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Send WhatsApp message.
        
        Args:
            to_phone: Recipient phone number
            message: Message text
            media_url: Optional media URL
            
        Returns:
            Send result
        """
        try:
            from app.services.communications.whatsapp_provider import WhatsAppProvider
            provider = WhatsAppProvider()
            result = await provider.send_message(
                to_phone=to_phone,
                message=message,
                media_url=media_url,
            )
            return result
        except Exception as e:
            logger.error(f"WhatsAppTool failed: {e}")
            return {"success": False, "error": str(e)}


class LeadLookupTool:
    """MCP Tool for looking up leads."""
    
    name = "lookup_lead"
    description = "Look up a lead by email or phone number"
    
    async def execute(
        self,
        tenant_id: str,
        identifier: str,
        identifier_type: str = "email",
        **kwargs,
    ) -> Dict[str, Any]:
        """Lookup lead.
        
        Args:
            tenant_id: Tenant UUID
            identifier: Email or phone number
            identifier_type: Type of identifier (email or phone)
            
        Returns:
            Lead information
        """
        try:
            from app.database.session import get_db
            from app.models.leads.lead import Lead
            from sqlalchemy import select
            
            db = next(get_db())
            
            if identifier_type == "email":
                stmt = select(Lead).where(
                    Lead.tenant_id == tenant_id,
                    Lead.email == identifier,
                )
            else:
                stmt = select(Lead).where(
                    Lead.tenant_id == tenant_id,
                    Lead.phone == identifier,
                )
            
            result = db.execute(stmt)
            lead = result.scalar_one_or_none()
            db.close()
            
            if not lead:
                return {"found": False, "lead": None}
            
            return {
                "found": True,
                "lead": {
                    "id": str(lead.id),
                    "email": lead.email,
                    "full_name": lead.full_name,
                    "company": lead.company,
                    "phone": lead.phone,
                    "status": lead.status,
                    "score": lead.revenue_score,
                },
            }
            
        except Exception as e:
            logger.error(f"LeadLookupTool failed: {e}")
            return {"found": False, "error": str(e)}


class CampaignTool:
    """MCP Tool for managing campaigns."""
    
    name = "manage_campaign"
    description = "Create, update, or get campaign information"
    
    async def execute(
        self,
        action: str,
        tenant_id: str,
        campaign_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute campaign action.
        
        Args:
            action: Action to perform (create, update, get, list, start, pause)
            tenant_id: Tenant UUID
            campaign_id: Campaign UUID (for get/update/start/pause)
            **kwargs: Additional parameters
            
        Returns:
            Action result
        """
        try:
            if action == "create":
                return await self._create_campaign(tenant_id, **kwargs)
            elif action == "get":
                return await self._get_campaign(campaign_id)
            elif action == "list":
                return await self._list_campaigns(tenant_id, **kwargs)
            elif action == "start":
                return await self._start_campaign(campaign_id)
            elif action == "pause":
                return await self._pause_campaign(campaign_id)
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            logger.error(f"CampaignTool failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _create_campaign(self, tenant_id: str, **kwargs) -> Dict[str, Any]:
        """Create a new campaign."""
        from app.database.session import get_db
        from app.models.campaigns import Campaign, CampaignStatus, CampaignType
        from uuid import uuid4
        
        db = next(get_db())
        
        try:
            campaign = Campaign(
                id=uuid4(),
                tenant_id=tenant_id,
                name=kwargs.get("name", "Untitled Campaign"),
                description=kwargs.get("description"),
                type=CampaignType(kwargs.get("type", "email")),
                status=CampaignStatus.DRAFT,
                subject=kwargs.get("subject"),
                body=kwargs.get("body", ""),
                image_url=kwargs.get("image_url"),
                start_date=kwargs.get("start_date"),
                end_date=kwargs.get("end_date"),
                target_audience=kwargs.get("target_audience"),
            )
            
            db.add(campaign)
            db.commit()
            db.refresh(campaign)
            
            return {
                "success": True,
                "campaign_id": str(campaign.id),
                "status": campaign.status.value,
            }
            
        finally:
            db.close()
    
    async def _get_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Get campaign details."""
        from app.database.session import get_db
        from app.models.campaigns import Campaign
        
        db = next(get_db())
        
        try:
            campaign = db.get(Campaign, campaign_id)
            if not campaign:
                return {"success": False, "error": "Campaign not found"}
            
            return {
                "success": True,
                "campaign": {
                    "id": str(campaign.id),
                    "name": campaign.name,
                    "type": campaign.type.value,
                    "status": campaign.status.value,
                    "sent_count": campaign.sent_count,
                    "delivered_count": campaign.delivered_count,
                    "opened_count": campaign.opened_count,
                    "replied_count": campaign.replied_count,
                },
            }
            
        finally:
            db.close()
    
    async def _list_campaigns(self, tenant_id: str, **kwargs) -> Dict[str, Any]:
        """List campaigns."""
        from app.database.session import get_db
        from app.models.campaigns import Campaign
        from sqlalchemy import select
        
        db = next(get_db())
        
        try:
            stmt = select(Campaign).where(Campaign.tenant_id == tenant_id)
            
            if kwargs.get("status"):
                stmt = stmt.where(Campaign.status == kwargs["status"])
            
            result = db.execute(stmt)
            campaigns = result.scalars().all()
            
            return {
                "success": True,
                "campaigns": [
                    {
                        "id": str(c.id),
                        "name": c.name,
                        "type": c.type.value,
                        "status": c.status.value,
                    }
                    for c in campaigns
                ],
            }
            
        finally:
            db.close()
    
    async def _start_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Start a campaign."""
        from app.database.session import get_db
        from app.models.campaigns import Campaign, CampaignStatus
        from app.services.campaigns.scheduler import execute_campaign
        
        db = next(get_db())
        
        try:
            campaign = db.get(Campaign, campaign_id)
            if not campaign:
                return {"success": False, "error": "Campaign not found"}
            
            campaign.status = CampaignStatus.SCHEDULED
            db.commit()
            
            # Queue for execution
            execute_campaign.delay(campaign_id)
            
            return {
                "success": True,
                "message": f"Campaign {campaign_id} started",
            }
            
        finally:
            db.close()
    
    async def _pause_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Pause a campaign."""
        from app.database.session import get_db
        from app.models.campaigns import Campaign, CampaignStatus
        
        db = next(get_db())
        
        try:
            campaign = db.get(Campaign, campaign_id)
            if not campaign:
                return {"success": False, "error": "Campaign not found"}
            
            campaign.status = CampaignStatus.PAUSED
            db.commit()
            
            return {
                "success": True,
                "message": f"Campaign {campaign_id} paused",
            }
            
        finally:
            db.close()


class KnowledgeSearchTool:
    """MCP Tool for searching knowledge base."""
    
    name = "search_knowledge"
    description = "Search the knowledge base for relevant information"
    
    async def execute(
        self,
        tenant_id: str,
        query: str,
        top_k: int = 3,
        **kwargs,
    ) -> Dict[str, Any]:
        """Search knowledge base.
        
        Args:
            tenant_id: Tenant UUID
            query: Search query
            top_k: Number of results
            
        Returns:
            Search results
        """
        try:
            from app.services.ai.model_manager import get_model_manager
            from app.services.ai.services.qdrant_service import get_qdrant_service
            
            manager = get_model_manager()
            
            # Generate embedding
            embedding_loader = await manager.get_model("embedding", "nomic-embed-text-v1.5")
            query_embedding = await embedding_loader.embed_query(query)
            
            # Search Qdrant
            qdrant = get_qdrant_service()
            results = await qdrant.search(
                tenant_id=tenant_id,
                query_vector=query_embedding,
                limit=top_k,
            )
            
            return {
                "success": True,
                "results": results,
                "count": len(results),
            }
            
        except Exception as e:
            logger.error(f"KnowledgeSearchTool failed: {e}")
            return {"success": False, "error": str(e), "results": []}


class ConversationTool:
    """MCP Tool for managing conversations."""
    
    name = "manage_conversation"
    description = "Get conversation history or create new conversation"
    
    async def execute(
        self,
        action: str,
        tenant_id: str,
        conversation_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute conversation action.
        
        Args:
            action: Action (get_history, create)
            tenant_id: Tenant UUID
            conversation_id: Conversation UUID
            
        Returns:
            Action result
        """
        try:
            if action == "get_history":
                return await self._get_history(conversation_id)
            elif action == "create":
                return await self._create_conversation(tenant_id, **kwargs)
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            logger.error(f"ConversationTool failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _get_history(self, conversation_id: str) -> Dict[str, Any]:
        """Get conversation history."""
        from app.database.session import get_db
        from app.models.campaigns import Conversation, Message
        from sqlalchemy import select
        
        db = next(get_db())
        
        try:
            conversation = db.get(Conversation, conversation_id)
            if not conversation:
                return {"success": False, "error": "Conversation not found"}
            
            stmt = select(Message).where(
                Message.conversation_id == conversation_id
            ).order_by(Message.created_at.asc()).limit(50)
            
            result = db.execute(stmt)
            messages = result.scalars().all()
            
            return {
                "success": True,
                "conversation_id": conversation_id,
                "messages": [
                    {
                        "id": str(m.id),
                        "direction": m.direction,
                        "content": m.content,
                        "created_at": m.created_at.isoformat(),
                    }
                    for m in messages
                ],
            }
            
        finally:
            db.close()
    
    async def _create_conversation(self, tenant_id: str, **kwargs) -> Dict[str, Any]:
        """Create new conversation."""
        from app.database.session import get_db
        from app.models.campaigns import Conversation
        from uuid import uuid4
        
        db = next(get_db())
        
        try:
            conversation = Conversation(
                id=uuid4(),
                tenant_id=tenant_id,
                lead_id=kwargs.get("lead_id", uuid4()),
                channel=kwargs.get("channel", "chat"),
                subject=kwargs.get("subject"),
                status="active",
                ai_enabled=True,
            )
            
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            
            return {
                "success": True,
                "conversation_id": str(conversation.id),
            }
            
        finally:
            db.close()


# MCP Tool Registry
MCP_TOOLS = {
    "send_email": EmailTool(),
    "send_whatsapp": WhatsAppTool(),
    "lookup_lead": LeadLookupTool(),
    "manage_campaign": CampaignTool(),
    "search_knowledge": KnowledgeSearchTool(),
    "manage_conversation": ConversationTool(),
}


def get_mcp_tools() -> Dict[str, Any]:
    """Get all available MCP tools.
    
    Returns:
        Dictionary of tool name to tool instance
    """
    return MCP_TOOLS


def get_tool(name: str) -> Optional[Any]:
    """Get a specific MCP tool by name.
    
    Args:
        name: Tool name
        
    Returns:
        Tool instance or None
    """
    return MCP_TOOLS.get(name)