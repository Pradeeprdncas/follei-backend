"""Inbound Message Engine - Process incoming messages from all channels."""
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger
from app.config.settings import get_settings

_settings = get_settings()


class InboundMessageEngine:
    """Processes incoming messages from email, WhatsApp, SMS.
    
    Flow:
    Webhook → Lead Lookup → Conversation History → RAG → AI Reply → Send Reply → Save
    """
    
    def __init__(self):
        """Initialize inbound message engine."""
        self.ai_enabled = True
    
    async def process_inbound_message(
        self,
        channel: str,
        tenant_id: str,
        sender_identifier: str,  # email or phone
        content: str,
        subject: Optional[str] = None,
        media_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process an incoming message from any channel.
        
        Args:
            channel: Channel type (email, whatsapp, sms, chat)
            tenant_id: Tenant UUID
            sender_identifier: Sender email or phone
            content: Message content
            subject: Email subject (optional)
            media_url: Media URL (optional)
            
        Returns:
            Processing result with AI response if generated
        """
        try:
            logger.info(f"Processing inbound {channel} message from {sender_identifier}")
            
            # 1. Lookup lead
            lead = await self._lookup_lead(tenant_id, sender_identifier, channel)
            if not lead:
                logger.warning(f"Lead not found for {sender_identifier}")
                return {
                    "success": False,
                    "error": "Lead not found",
                    "ai_response": None,
                }
            
            # 2. Get or create conversation
            conversation = await self._get_or_create_conversation(
                tenant_id=tenant_id,
                lead_id=lead.id,
                channel=channel,
                subject=subject,
            )
            
            # 3. Save inbound message
            inbound_msg = await self._save_message(
                conversation_id=conversation.id,
                tenant_id=tenant_id,
                lead_id=lead.id,
                channel=channel,
                direction="inbound",
                content=content,
                subject=subject,
                attachments=[media_url] if media_url else None,
            )
            
            # 4. Update conversation stats
            conversation.message_count += 1
            conversation.last_message_at = datetime.utcnow()
            
            # 5. Generate AI response if enabled
            ai_response = None
            if self.ai_enabled and conversation.ai_enabled:
                ai_response = await self._generate_ai_response(
                    tenant_id=tenant_id,
                    lead_id=lead.id,
                    conversation_id=conversation.id,
                    message=content,
                    channel=channel,
                )
                
                if ai_response:
                    # 6. Save AI response
                    outbound_msg = await self._save_message(
                        conversation_id=conversation.id,
                        tenant_id=tenant_id,
                        lead_id=lead.id,
                        channel=channel,
                        direction="outbound",
                        content=ai_response["answer"],
                        is_ai_generated=True,
                        ai_confidence=ai_response.get("confidence", 0),
                        ai_intent=ai_response.get("intent"),
                    )
                    
                    conversation.message_count += 1
                    conversation.last_message_at = datetime.utcnow()
                    conversation.last_ai_response_at = datetime.utcnow()
                    
                    # 7. Send reply via appropriate channel
                    send_result = await self._send_reply(
                        channel=channel,
                        tenant_id=tenant_id,
                        lead=lead,
                        message=ai_response["answer"],
                        media_url=None,
                    )
                    
                    if not send_result.get("success"):
                        logger.error(f"Failed to send reply: {send_result.get('error')}")
            
            # Commit conversation updates
            from app.database.session import get_db
            db = next(get_db())
            db.merge(conversation)
            db.commit()
            db.close()
            
            return {
                "success": True,
                "lead_id": str(lead.id),
                "conversation_id": str(conversation.id),
                "message_id": str(inbound_msg.id),
                "ai_response": ai_response,
            }
            
        except Exception as e:
            logger.error(f"Failed to process inbound message: {e}")
            return {
                "success": False,
                "error": str(e),
                "ai_response": None,
            }
    
    async def _lookup_lead(self, tenant_id: str, identifier: str, channel: str):
        """Lookup lead by email or phone."""
        try:
            from app.database.session import get_db
            from app.models.leads.lead import Lead
            from sqlalchemy import select
            
            db = next(get_db())
            
            # Search by email or phone
            if channel == "email":
                stmt = select(Lead).where(
                    Lead.tenant_id == tenant_id,
                    Lead.email == identifier,
                )
            else:  # whatsapp, sms
                stmt = select(Lead).where(
                    Lead.tenant_id == tenant_id,
                    Lead.phone == identifier,
                )
            
            result = db.execute(stmt)
            lead = result.scalar_one_or_none()
            db.close()
            
            return lead
            
        except Exception as e:
            logger.error(f"Failed to lookup lead: {e}")
            return None
    
    async def _get_or_create_conversation(
        self,
        tenant_id: str,
        lead_id: str,
        channel: str,
        subject: Optional[str] = None,
    ):
        """Get existing or create new conversation."""
        try:
            from app.database.session import get_db
            from app.models.campaigns import Conversation
            from sqlalchemy import select
            import uuid
            
            db = next(get_db())
            
            # Look for active conversation
            stmt = select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.lead_id == lead_id,
                Conversation.channel == channel,
                Conversation.status == "active",
            ).order_by(Conversation.created_at.desc())
            
            result = db.execute(stmt)
            conversation = result.scalar_one_or_none()
            
            if not conversation:
                # Create new conversation
                conversation = Conversation(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    lead_id=lead_id,
                    channel=channel,
                    subject=subject,
                    status="active",
                    ai_enabled=True,
                    message_count=0,
                )
                db.add(conversation)
                db.commit()
            
            db.close()
            return conversation
            
        except Exception as e:
            logger.error(f"Failed to get/create conversation: {e}")
            raise
    
    async def _save_message(
        self,
        conversation_id: str,
        tenant_id: str,
        lead_id: str,
        channel: str,
        direction: str,
        content: str,
        subject: Optional[str] = None,
        attachments: Optional[list] = None,
        is_ai_generated: bool = False,
        ai_confidence: Optional[int] = None,
        ai_intent: Optional[str] = None,
    ):
        """Save message to database."""
        try:
            from app.database.session import get_db
            from app.models.campaigns import Message
            import uuid
            import json
            
            db = next(get_db())
            
            msg = Message(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                lead_id=lead_id,
                direction=direction,
                channel=channel,
                content=content,
                subject=subject,
                attachments=json.dumps(attachments) if attachments else None,
                is_ai_generated=is_ai_generated,
                ai_confidence=ai_confidence,
                ai_intent=ai_intent,
                read=(direction == "outbound"),
            )
            
            db.add(msg)
            db.commit()
            db.refresh(msg)
            db.close()
            
            return msg
            
        except Exception as e:
            logger.error(f"Failed to save message: {e}")
            raise
    
    async def _generate_ai_response(
        self,
        tenant_id: str,
        lead_id: str,
        conversation_id: str,
        message: str,
        channel: str,
    ) -> Optional[Dict[str, Any]]:
        """Generate AI response using RAG."""
        try:
            from app.services.ai.router import get_ai_router
            
            router = get_ai_router()
            
            # Build context
            context = {
                "tenant_id": tenant_id,
                "lead_id": lead_id,
                "conversation_id": conversation_id,
                "channel": channel,
            }
            
            # Process through AI router
            result = await router.process_auto_reply(
                message=message,
                tenant_id=tenant_id,
                lead_id=lead_id,
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to generate AI response: {e}")
            return None
    
    async def _send_reply(
        self,
        channel: str,
        tenant_id: str,
        lead,
        message: str,
        media_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send reply via appropriate channel."""
        try:
            if channel == "email":
                from app.services.communications.email_provider import EmailProvider
                provider = EmailProvider()
                return await provider.send_email(
                    to_email=lead.email,
                    to_name=lead.full_name or "Valued Customer",
                    subject="Re: " + (lead.conversations[0].subject if lead.conversations else "Your message"),
                    body=message,
                )
            
            elif channel == "whatsapp":
                from app.services.communications.whatsapp_provider import WhatsAppProvider
                provider = WhatsAppProvider()
                return await provider.send_message(
                    to_phone=lead.phone,
                    message=message,
                    media_url=media_url,
                )
            
            else:
                return {"success": False, "error": f"Unsupported channel: {channel}"}
                
        except Exception as e:
            logger.error(f"Failed to send reply: {e}")
            return {"success": False, "error": str(e)}