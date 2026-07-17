"""Analytics service."""
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.campaigns import Campaign, CampaignMessage, DeliveryStatus
from app.models.conversations.conversation import Message
from app.models.leads.lead import Lead
from app.repositories.campaign import CampaignRepository
from app.repositories.campaign_message import CampaignMessageRepository
from app.repositories.lead import LeadRepository


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_overview(self, tenant_id: str) -> dict:
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        total_leads = (await self.db.execute(
            select(func.count()).select_from(Lead).where(Lead.tenant_id == tenant_id)
        )).scalar() or 0
        new_leads = (await self.db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.tenant_id == tenant_id, Lead.created_at >= thirty_days_ago)
        )).scalar() or 0
        campaigns_running = (await self.db.execute(
            select(func.count()).select_from(Campaign).where(
                Campaign.tenant_id == tenant_id, Campaign.status == "running")
        )).scalar() or 0
        messages_sent = (await self.db.execute(
            select(func.count()).select_from(Message).where(
                Message.tenant_id == tenant_id, Message.direction == "outbound")
        )).scalar() or 0
        replies_received = (await self.db.execute(
            select(func.count()).select_from(Message).where(
                Message.tenant_id == tenant_id, Message.direction == "inbound")
        )).scalar() or 0
        conversion_rate = (replies_received / messages_sent * 100) if messages_sent > 0 else 0
        return {
            "total_leads": total_leads, "new_leads": new_leads,
            "campaigns_running": campaigns_running,
            "messages_sent": messages_sent, "replies_received": replies_received,
            "conversion_rate": round(conversion_rate, 2),
            "period": "last_30_days",
        }

    async def get_campaign_performance(self, campaign_id: str) -> dict:
        campaign = await self.db.get(Campaign, campaign_id)
        if not campaign:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Campaign not found")
        result = await self.db.execute(
            select(CampaignMessage).where(CampaignMessage.campaign_id == campaign_id)
        )
        messages = result.scalars().all()
        stats = {"total": len(messages), "sent": 0, "delivered": 0,
                 "opened": 0, "clicked": 0, "replied": 0, "failed": 0}
        for msg in messages:
            if msg.status == DeliveryStatus.SENT: stats["sent"] += 1
            elif msg.status == DeliveryStatus.DELIVERED: stats["delivered"] += 1; stats["sent"] += 1
            elif msg.status == DeliveryStatus.OPENED: stats["opened"] += 1; stats["delivered"] += 1; stats["sent"] += 1
            elif msg.status == DeliveryStatus.CLICKED: stats["clicked"] += 1
            elif msg.status == DeliveryStatus.REPLIED: stats["replied"] += 1
            elif msg.status == DeliveryStatus.FAILED: stats["failed"] += 1
        delivery_rate = (stats["delivered"] / stats["sent"] * 100) if stats["sent"] > 0 else 0
        open_rate = (stats["opened"] / stats["delivered"] * 100) if stats["delivered"] > 0 else 0
        click_rate = (stats["clicked"] / stats["delivered"] * 100) if stats["delivered"] > 0 else 0
        reply_rate = (stats["replied"] / stats["delivered"] * 100) if stats["delivered"] > 0 else 0
        return {
            "campaign_id": campaign_id, "campaign_name": campaign.name,
            "stats": stats,
            "rates": {
                "delivery_rate": round(delivery_rate, 2),
                "open_rate": round(open_rate, 2),
                "click_rate": round(click_rate, 2),
                "reply_rate": round(reply_rate, 2),
            },
        }

    async def get_lead_stats(self, tenant_id: str) -> dict:
        total = (await self.db.execute(
            select(func.count()).select_from(Lead).where(Lead.tenant_id == tenant_id)
        )).scalar() or 0
        hot = (await self.db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.tenant_id == tenant_id, Lead.current_temperature == "hot")
        )).scalar() or 0
        warm = (await self.db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.tenant_id == tenant_id, Lead.current_temperature == "warm")
        )).scalar() or 0
        cold = (await self.db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.tenant_id == tenant_id, Lead.current_temperature == "cold")
        )).scalar() or 0
        return {"total": total, "hot": hot, "warm": warm, "cold": cold}
