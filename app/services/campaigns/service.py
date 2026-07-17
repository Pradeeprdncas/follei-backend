"""Campaign service — orchestrates campaign lifecycle with outbox + events."""
from __future__ import annotations
from uuid import uuid4
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.orm import Session
from loguru import logger

from app.models.campaigns import (
    Campaign, CampaignMessage, CampaignMetric, InboundEmail,
    CampaignStatus, CampaignType, DeliveryStatus,
)
from app.models.leads.lead import Lead
from app.repositories.campaign import CampaignRepository
from app.repositories.campaign_message import CampaignMessageRepository
from app.repositories.campaign_metric import CampaignMetricRepository
from app.repositories.inbound_email import InboundEmailRepository
from app.repositories.lead import LeadRepository
from app.repositories.outbox import OutboxRepository
from app.schemas.campaign import (
    CampaignCreateRequest, CampaignUpdateRequest,
    CampaignResponse, CampaignMessageResponse, CampaignStatsResponse,
    CampaignMetricResponse, CampaignInboundEmailResponse,
)
from app.services.communications.router import CommunicationRouter
from app.services.communications.outbox import OutboxService
from app.services.communications.retry import RetryEngine
from app.services.communications.events import publish_event
from app.services.communications.streams.redis_streams import push_tracking_event
from app.events.base import (
    EVENT_CAMPAIGN_CREATED, EVENT_CAMPAIGN_SCHEDULED,
    EVENT_CAMPAIGN_STARTED, EVENT_CAMPAIGN_PAUSED,
    EVENT_CAMPAIGN_COMPLETED, EVENT_CAMPAIGN_CANCELLED,
    EVENT_CAMPAIGN_FAILED,
)


BATCH_SIZE = 100
_ALLOWED_START_STATUSES = {CampaignStatus.DRAFT, CampaignStatus.SCHEDULED, CampaignStatus.PAUSED}
_STAT_FIELD_MAP = {
    DeliveryStatus.DELIVERED: "delivered_count",
    DeliveryStatus.BOUNCED: "bounced_count",
    DeliveryStatus.FAILED: "failed_count",
    DeliveryStatus.REPLIED: "replied_count",
    DeliveryStatus.UNSUBSCRIBED: "unsubscribe_count",
    DeliveryStatus.OPENED: "opened_count",
    DeliveryStatus.CLICKED: "clicked_count",
}


def _campaign_to_response(c: Campaign) -> CampaignResponse:
    return CampaignResponse(
        id=str(c.id), name=c.name, description=c.description,
        type=c.type, status=c.status, subject=c.subject,
        body=c.body, image_url=c.image_url,
        start_date=c.start_date, end_date=c.end_date,
        schedule_config=c.schedule_config,
        target_audience=c.target_audience,
        tracking_config=c.tracking_config,
        analytics=c.analytics,
        metadata_=c.metadata_,
        total_recipients=c.total_recipients, sent_count=c.sent_count,
        delivered_count=c.delivered_count, opened_count=c.opened_count,
        clicked_count=c.clicked_count, replied_count=c.replied_count,
        bounced_count=c.bounced_count,
        failed_count=c.failed_count, tenant_id=str(c.tenant_id),
        created_at=c.created_at, updated_at=c.updated_at,
    )


def _message_to_response(m: CampaignMessage) -> CampaignMessageResponse:
    return CampaignMessageResponse(
        id=str(m.id), campaign_id=str(m.campaign_id),
        lead_id=str(m.lead_id), channel=m.channel,
        recipient=m.recipient, subject=m.subject,
        body=m.body, image_url=m.image_url,
        status=m.status, sent_at=m.sent_at,
        delivered_at=m.delivered_at, opened_at=m.opened_at,
        clicked_at=m.clicked_at, replied_at=m.replied_at,
        failed_at=m.failed_at, error_message=m.error_message,
        created_at=m.created_at,
    )


class CampaignService:
    def __init__(self, db: Session, router: CommunicationRouter | None = None,
                 outbox_service: OutboxService | None = None):
        self.db = db
        self.campaign_repo = CampaignRepository(db)
        self.message_repo = CampaignMessageRepository(db)
        self.metric_repo = CampaignMetricRepository(db)
        self.inbound_repo = InboundEmailRepository(db)
        self.lead_repo = LeadRepository(db)
        self.outbox_repo = OutboxRepository(db)
        self.router = router or CommunicationRouter()
        retry_engine = RetryEngine(self.outbox_repo)
        self.outbox_service = outbox_service or OutboxService(
            self.outbox_repo, self.router, retry_engine,
        )

    def _channel_for_campaign(self, campaign_type: CampaignType) -> str:
        return {
            CampaignType.EMAIL: "email",
            CampaignType.WHATSAPP: "whatsapp",
            CampaignType.SMS: "sms",
            CampaignType.VOICE: "voice",
            CampaignType.MULTI_CHANNEL: "email",
        }.get(campaign_type, "email")

    def _get_campaign(self, campaign_id: str) -> Campaign:
        campaign = self.campaign_repo.get_campaign(campaign_id)
        if not campaign:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        return campaign

    def create(self, payload: CampaignCreateRequest) -> CampaignResponse:
        campaign = Campaign(
            id=uuid4(), tenant_id=payload.tenant_id,
            name=payload.name, description=payload.description,
            type=payload.type, status=CampaignStatus.DRAFT,
            subject=payload.subject, body=payload.body,
            image_url=payload.image_url,
            start_date=payload.start_date, end_date=payload.end_date,
            schedule_config=payload.schedule_config,
            target_audience=payload.target_audience,
            tracking_config=payload.tracking_config,
            metadata_=payload.metadata_,
        )
        self.campaign_repo.create_campaign(campaign)
        publish_event(EVENT_CAMPAIGN_CREATED, str(payload.tenant_id), {
            "campaign_id": str(campaign.id), "name": campaign.name,
            "type": campaign.type.value,
        })
        return _campaign_to_response(campaign)

    def get_response(self, campaign_id: str) -> CampaignResponse:
        return _campaign_to_response(self._get_campaign(campaign_id))

    def update(self, campaign_id: str, payload: CampaignUpdateRequest) -> CampaignResponse:
        campaign = self._get_campaign(campaign_id)
        for field in ("name", "description", "subject", "body", "image_url",
                       "start_date", "end_date", "target_audience",
                       "schedule_config", "tracking_config", "metadata_", "status"):
            val = getattr(payload, field, None)
            if val is not None:
                setattr(campaign, field, val)
        campaign.updated_at = datetime.now(timezone.utc)
        self.campaign_repo.update_campaign(campaign)
        return _campaign_to_response(campaign)

    def delete(self, campaign_id: str) -> None:
        self._get_campaign(campaign_id)
        self.campaign_repo.delete_campaign(campaign_id)

    def list(self, tenant_id: str, status_filter: str | None = None,
             type_filter: str | None = None, page: int = 1,
             page_size: int = 20) -> Any:
        campaigns, total = self.campaign_repo.list_campaigns(
            tenant_id, status_filter, type_filter, page, page_size)
        items = [_campaign_to_response(c) for c in campaigns]
        from app.schemas.campaign import CampaignListResponse
        return CampaignListResponse(items=items, total=total, page=page, page_size=page_size)

    def schedule(self, campaign_id: str, start_date: datetime | None = None) -> CampaignResponse:
        campaign = self._get_campaign(campaign_id)
        if campaign.status != CampaignStatus.DRAFT:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Cannot schedule campaign in {campaign.status.value} status")
        campaign.status = CampaignStatus.SCHEDULED
        if start_date:
            campaign.start_date = start_date
        campaign.updated_at = datetime.now(timezone.utc)
        self.campaign_repo.update_campaign(campaign)
        publish_event(EVENT_CAMPAIGN_SCHEDULED, str(campaign.tenant_id), {
            "campaign_id": campaign_id, "start_date": str(start_date or campaign.start_date),
        })
        return _campaign_to_response(campaign)

    def pause(self, campaign_id: str) -> CampaignResponse:
        campaign = self._get_campaign(campaign_id)
        if campaign.status != CampaignStatus.RUNNING:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Only running campaigns can be paused")
        campaign.status = CampaignStatus.PAUSED
        campaign.updated_at = datetime.now(timezone.utc)
        self.campaign_repo.update_campaign(campaign)
        publish_event(EVENT_CAMPAIGN_PAUSED, str(campaign.tenant_id), {
            "campaign_id": campaign_id,
        })
        return _campaign_to_response(campaign)

    def cancel(self, campaign_id: str) -> CampaignResponse:
        campaign = self._get_campaign(campaign_id)
        if campaign.status in (CampaignStatus.COMPLETED, CampaignStatus.FAILED):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Cannot cancel campaign in {campaign.status.value} status")
        campaign.status = CampaignStatus.FAILED
        campaign.updated_at = datetime.now(timezone.utc)
        self.campaign_repo.update_campaign(campaign)
        publish_event(EVENT_CAMPAIGN_CANCELLED, str(campaign.tenant_id), {
            "campaign_id": campaign_id,
        })
        return _campaign_to_response(campaign)

    async def start(self, campaign_id: str) -> dict:
        campaign = self._get_campaign(campaign_id)
        if campaign.status not in _ALLOWED_START_STATUSES:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Cannot start campaign in {campaign.status.value} status")

        locked = self.campaign_repo.set_processing(campaign_id)
        if not locked:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail="Campaign is already being processed")

        publish_event(EVENT_CAMPAIGN_STARTED, str(campaign.tenant_id), {
            "campaign_id": campaign_id,
        })

        try:
            channel = self._channel_for_campaign(campaign.type)
            leads = self.lead_repo.get_by_tenant(campaign.tenant_id)
            total = len(leads)
            sent = failed = 0
            results = []

            for i in range(0, total, BATCH_SIZE):
                batch = leads[i:i + BATCH_SIZE]
                batch_messages = []

                for lead in batch:
                    recipient = (
                        lead.email
                        if campaign.type in (CampaignType.EMAIL, CampaignType.MULTI_CHANNEL)
                        else str(lead.phone or "")
                    )
                    cm = CampaignMessage(
                        id=uuid4(), campaign_id=campaign.id, lead_id=lead.id,
                        channel=campaign.type, recipient=recipient,
                        subject=campaign.subject, body=campaign.body,
                        image_url=campaign.image_url,
                        status=DeliveryStatus.PENDING,
                    )
                    self.db.add(cm)
                    batch_messages.append((lead, cm, recipient))

                self.db.flush()

                for lead, cm, recipient in batch_messages:
                    try:
                        if campaign.type == CampaignType.MULTI_CHANNEL:
                            channel = lead.email and "email" or "whatsapp"
                            if lead.phone and not lead.email:
                                channel = "whatsapp"

                        self.outbox_service.enqueue(
                            tenant_id=str(campaign.tenant_id),
                            channel=channel,
                            recipient=recipient,
                            subject=campaign.subject,
                            body=campaign.body,
                            campaign_id=str(campaign.id),
                            campaign_message_id=str(cm.id),
                            metadata={"lead_id": str(lead.id), "image_url": campaign.image_url or ""},
                            priority=1,
                        )
                        cm.status = DeliveryStatus.QUEUED
                        sent += 1
                    except Exception as e:
                        cm.status = DeliveryStatus.FAILED
                        cm.failed_at = datetime.now(timezone.utc)
                        cm.error_message = str(e)[:2000]
                        failed += 1

                    results.append({
                        "lead_id": str(cm.lead_id), "recipient": cm.recipient,
                        "status": cm.status.value,
                    })

                self.db.flush()

            self.campaign_repo.set_stats(
                campaign.id,
                sent_count=sent, failed_count=failed,
                total_recipients=total, status=CampaignStatus.COMPLETED,
            )
            publish_event(EVENT_CAMPAIGN_COMPLETED, str(campaign.tenant_id), {
                "campaign_id": campaign_id, "total": total, "sent": sent, "failed": failed,
            })

            return {"campaign_id": campaign_id, "status": "completed",
                    "total": total, "sent": sent, "failed": failed, "results": results}

        except Exception:
            self.db.rollback()
            self.campaign_repo.mark_status(campaign_id, CampaignStatus.FAILED)
            self.campaign_repo.clear_processing(campaign_id)
            publish_event(EVENT_CAMPAIGN_FAILED, str(campaign.tenant_id), {
                "campaign_id": campaign_id,
            })
            raise

    def get_stats(self, campaign_id: str) -> CampaignStatsResponse:
        campaign = self._get_campaign(campaign_id)
        stats = self.message_repo.get_statistics_by_campaign(campaign_id)
        sent = stats.get("sent", 0)
        delivered = stats.get("delivered", 0)
        opened = stats.get("opened", 0)
        clicked = stats.get("clicked", 0)
        replied = stats.get("replied", 0)
        bounced = stats.get("bounced", 0)
        failed = stats.get("failed", 0)
        total = stats.get("total", 0)

        delivery_rate = (delivered / sent * 100) if sent > 0 else 0
        open_rate = (opened / delivered * 100) if delivered > 0 else 0
        click_rate = (clicked / delivered * 100) if delivered > 0 else 0
        reply_rate = (replied / delivered * 100) if delivered > 0 else 0

        return CampaignStatsResponse(
            campaign_id=str(campaign.id), total_recipients=total,
            sent=sent, delivered=delivered, opened=opened,
            clicked=clicked, replied=replied, bounced=bounced, failed=failed,
            delivery_rate=delivery_rate, open_rate=open_rate,
            click_rate=click_rate, reply_rate=reply_rate,
        )

    def get_analytics(self, campaign_id: str) -> dict:
        campaign = self._get_campaign(campaign_id)
        stats = self.message_repo.get_statistics_by_campaign(campaign_id)
        rates = {}
        sent = stats.get("sent", 0)
        delivered = stats.get("delivered", 0)
        if sent > 0:
            rates["delivery_rate"] = round(stats.get("delivered", 0) / sent * 100, 2)
        if delivered > 0:
            rates["open_rate"] = round(stats.get("opened", 0) / delivered * 100, 2)
            rates["click_rate"] = round(stats.get("clicked", 0) / delivered * 100, 2)
            rates["reply_rate"] = round(stats.get("replied", 0) / delivered * 100, 2)
        return {"campaign_id": campaign_id, "campaign_name": campaign.name,
                "stats": stats, "rates": rates}

    def add_lead(self, campaign_id: str, lead_id: str) -> dict:
        campaign = self._get_campaign(campaign_id)
        lead = self.lead_repo.get_by_id(lead_id)
        if not lead:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Lead not found")
        existing = self.message_repo.get_by_campaign(campaign_id)
        if any(str(m.lead_id) == lead_id for m in existing):
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail="Lead already in campaign")
        recipient = lead.email if campaign.type in (CampaignType.EMAIL, CampaignType.MULTI_CHANNEL) else str(lead.phone or "")
        self.message_repo.bulk_insert([
            CampaignMessage(
                id=uuid4(), campaign_id=campaign_id, lead_id=lead_id,
                channel=campaign.type, recipient=recipient,
                subject=campaign.subject, body=campaign.body,
            )
        ])
        return {"message": "Lead added to campaign", "campaign_id": campaign_id, "lead_id": lead_id}

    def remove_lead(self, campaign_id: str, lead_id: str) -> None:
        self._get_campaign(campaign_id)
        messages = self.message_repo.get_by_campaign(campaign_id)
        target = None
        for m in messages:
            if str(m.lead_id) == lead_id:
                target = m
                break
        if not target:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Lead not found in campaign")
        self.message_repo.delete(target.id)

    def list_leads(self, campaign_id: str) -> dict:
        self._get_campaign(campaign_id)
        messages = self.message_repo.get_by_campaign(campaign_id)
        items = [_message_to_response(m) for m in messages]
        return {"campaign_id": campaign_id, "leads": items, "total": len(items)}

    def track_open(self, message_id: str, campaign_id: str, tenant_id: str) -> None:
        push_tracking_event("track.open", tenant_id, campaign_id, message_id)

    def track_click(self, message_id: str, campaign_id: str, tenant_id: str) -> None:
        push_tracking_event("track.click", tenant_id, campaign_id, message_id)

    def track_delivery(self, message_id: str, campaign_id: str, tenant_id: str,
                       status: DeliveryStatus,
                       provider_id: str | None = None, error: str | None = None) -> None:
        push_tracking_event("track.delivery", tenant_id, campaign_id, message_id, {
            "status": status.value, "provider_id": provider_id, "error": error,
        })

    def track_bounce(self, message_id: str, campaign_id: str, tenant_id: str,
                     error: str | None = None) -> None:
        push_tracking_event("track.bounce", tenant_id, campaign_id, message_id, {
            "error": error or "",
        })

    def record_reply(self, message_id: str, campaign_id: str, tenant_id: str) -> None:
        push_tracking_event("track.reply", tenant_id, campaign_id, message_id)

    def create_inbound_email(self, tenant_id: str, campaign_id: str | None,
                              lead_id: str | None, from_email: str | None,
                              to_email: str | None, subject: str | None,
                              body: str | None, provider: str,
                              event_type: str, raw_payload: dict) -> InboundEmail:
        inbound = InboundEmail(
            id=uuid4(), tenant_id=tenant_id, campaign_id=campaign_id,
            lead_id=lead_id, from_email=from_email, to_email=to_email,
            subject=subject, body=body, provider=provider,
            event_type=event_type, raw_payload=raw_payload,
        )
        self.inbound_repo.create(inbound)
        return inbound

    def list_inbound_emails(self, tenant_id: str | None = None,
                            campaign_id: str | None = None,
                            lead_id: str | None = None,
                            page: int = 1, page_size: int = 20) -> tuple[list, int]: # Changed from list[InboundEmail] to lis
        items = self.inbound_repo.list_all()
        if tenant_id:
            items = [i for i in items if str(i.tenant_id) == tenant_id]
        if campaign_id:
            items = [i for i in items if i.campaign_id and str(i.campaign_id) == campaign_id]
        if lead_id:
            items = [i for i in items if i.lead_id and str(i.lead_id) == lead_id]
        total = len(items)
        start = (page - 1) * page_size
        return items[start:start + page_size], total

    def create_metric(self, tenant_id: str, campaign_id: str,
                      metric_type: str, value: int = 1,
                      metadata_: dict | None = None) -> CampaignMetric:
        metric = CampaignMetric(
            id=uuid4(), campaign_id=campaign_id, tenant_id=tenant_id,
            metric_type=metric_type, value=value, metadata_=metadata_,
        )
        self.metric_repo.create(metric)
        return metric

    def list_metrics(self, campaign_id: str | None = None,
                     metric_type: str | None = None,
                     page: int = 1, page_size: int = 20) -> tuple[list[CampaignMetric], int]:
        items = self.metric_repo.list_all()
        if campaign_id:
            items = self.metric_repo.get_by_campaign(campaign_id)
        if metric_type:
            items = [i for i in items if i.metric_type == metric_type]
        total = len(items)
        start = (page - 1) * page_size
        return items[start:start + page_size], total

    def get_metric(self, metric_id: str) -> CampaignMetric | None:
        return self.metric_repo.get_by_id(metric_id)

    def delete_metric(self, metric_id: str) -> bool:
        return self.metric_repo.delete(metric_id)

    def resolve_inbound_context(self, from_email: str | None,
                                 tenant_id: str | None,
                                 campaign_id: str | None,
                                 lead_id: str | None) -> tuple[str | None, str | None, str | None]:
        if from_email and not lead_id:
            leads = self.lead_repo.list_all()
            for lead in leads:
                if lead.email and lead.email.lower() == from_email.lower():
                    lead_id = str(lead.id)
                    tenant_id = tenant_id or str(lead.tenant_id)
                    break

        if campaign_id:
            try:
                campaign = self._get_campaign(campaign_id)
                tenant_id = tenant_id or str(campaign.tenant_id)
            except Exception:
                pass

        return tenant_id, campaign_id, lead_id
