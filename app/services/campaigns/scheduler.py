"""Campaign Scheduler - Celery-based campaign execution with outbox pattern."""
import asyncio
from typing import Optional
from datetime import datetime
from loguru import logger
from celery import Celery
from celery.schedules import crontab

from app.config.settings import get_settings

_settings = get_settings()

celery_app = Celery(
    "campaigns",
    broker=_settings.REDIS_URL or "redis://localhost:6379/0",
    backend=_settings.REDIS_URL or "redis://localhost:6379/0",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3500,
)

celery_app.conf.beat_schedule = {
    "check-scheduled-campaigns": {
        "task": "app.services.campaigns.scheduler.check_scheduled_campaigns",
        "schedule": crontab(minute="*/1"),
    },
    "update-campaign-stats": {
        "task": "app.services.campaigns.scheduler.update_campaign_stats",
        "schedule": crontab(minute="*/5"),
    },
    "process-outbox-emails": {
        "task": "app.services.campaigns.scheduler.process_outbox_emails",
        "schedule": crontab(minute="*/1"),
    },
    "process-outbox-whatsapp": {
        "task": "app.services.campaigns.scheduler.process_outbox_whatsapp",
        "schedule": crontab(minute="*/1"),
    },
    "retry-failed-outbox": {
        "task": "app.services.campaigns.scheduler.retry_failed_outbox",
        "schedule": crontab(minute="*/5"),
    },
    "process-tracking-events": {
        "task": "app.services.campaigns.scheduler.process_tracking_events",
        "schedule": crontab(minute="*/1"),
    },
    "cleanup-outbox": {
        "task": "app.services.campaigns.scheduler.cleanup_outbox",
        "schedule": crontab(hour="*/6"),
    },
}


def _run_async(coro):
    """Safely run an async coroutine from a sync Celery task."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    return loop.run_until_complete(coro)


def _get_service():
    from app.database.session import get_db
    from app.services.campaigns.service import CampaignService
    db = next(get_db())
    return CampaignService(db), db


@celery_app.task(bind=True, max_retries=3)
def check_scheduled_campaigns(self):
    try:
        from app.database.session import get_db
        from app.repositories.campaign import CampaignRepository

        db = next(get_db())
        repo = CampaignRepository(db)
        campaigns = repo.get_scheduled_pending()

        started = 0
        for campaign in campaigns:
            logger.info(f"Starting scheduled campaign: {campaign.id} - {campaign.name}")
            execute_campaign.delay(str(campaign.id))
            started += 1

        db.close()
        return {"checked": len(campaigns), "started": started}

    except Exception as e:
        logger.error(f"Failed to check scheduled campaigns: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def execute_campaign(self, campaign_id: str):
    try:
        svc, db = _get_service()
        try:
            result = _run_async(svc.start(campaign_id))
            logger.info(f"Campaign {campaign_id} executed: {result}")
            return result
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to execute campaign {campaign_id}: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def send_email_message(self, message_id: str, to_email: str, to_name: str,
                       subject: str, body: str, image_url: Optional[str] = None):
    try:
        from app.services.communications.router import CommunicationRouter
        from app.models.campaigns import DeliveryStatus
        from app.database.session import get_db
        from app.repositories.outbox import OutboxRepository

        db = next(get_db())
        try:
            repo = OutboxRepository(db)
            router = CommunicationRouter()
            result = _run_async(router.send(
                channel="email", recipient=to_email,
                subject=subject, body=body,
                metadata={"to_name": to_name, "image_url": image_url or ""},
            ))
            if result.success:
                repo.mark_sent(message_id, result.provider_message_id, "brevo", result.raw_response)
            else:
                repo.mark_failed(message_id, result.error or "Unknown error")
            db.commit()
            return {"success": result.success, "message_id": message_id}
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to send email message {message_id}: {e}")
        raise self.retry(exc=e, countdown=30)


@celery_app.task(bind=True, max_retries=3)
def send_whatsapp_message(self, message_id: str, to_phone: str, body: str,
                          image_url: Optional[str] = None):
    try:
        from app.services.communications.router import CommunicationRouter
        from app.database.session import get_db
        from app.repositories.outbox import OutboxRepository

        db = next(get_db())
        try:
            repo = OutboxRepository(db)
            router = CommunicationRouter()
            result = _run_async(router.send(
                channel="whatsapp", recipient=to_phone,
                subject=None, body=body,
                metadata={"image_url": image_url or ""},
            ))
            if result.success:
                repo.mark_sent(message_id, result.provider_message_id, "meta_whatsapp", result.raw_response)
            else:
                repo.mark_failed(message_id, result.error or "Unknown error")
            db.commit()
            return {"success": result.success, "message_id": message_id}
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message {message_id}: {e}")
        raise self.retry(exc=e, countdown=30)


@celery_app.task
def update_campaign_stats():
    try:
        from app.models.campaigns import CampaignStatus
        from app.repositories.campaign import CampaignRepository
        from app.repositories.campaign_message import CampaignMessageRepository
        from app.database.session import get_db

        db = next(get_db())
        repo = CampaignRepository(db)
        msg_repo = CampaignMessageRepository(db)

        campaigns = repo.get_by_status_all(CampaignStatus.RUNNING)

        for campaign in campaigns:
            stats = msg_repo.get_statistics_by_campaign(campaign.id)
            repo.set_stats(
                campaign.id,
                sent_count=stats.get("sent", 0),
                delivered_count=stats.get("delivered", 0),
                opened_count=stats.get("opened", 0),
                clicked_count=stats.get("clicked", 0),
                replied_count=stats.get("replied", 0),
                bounced_count=stats.get("bounced", 0),
                failed_count=stats.get("failed", 0),
            )

        db.close()
        return {"updated": len(campaigns)}

    except Exception as e:
        logger.error(f"Failed to update campaign stats: {e}")
        return {"error": str(e)}


@celery_app.task
def process_outbox_emails():
    try:
        from app.services.communications.workers.email_worker import EmailWorker
        worker = EmailWorker()
        processed = worker.run_once(batch_size=20)
        return {"processed": processed}
    except Exception as e:
        logger.error(f"Outbox email processing failed: {e}")
        return {"error": str(e)}


@celery_app.task
def process_outbox_whatsapp():
    try:
        from app.services.communications.workers.whatsapp_worker import WhatsAppWorker
        worker = WhatsAppWorker()
        processed = worker.run_once(batch_size=20)
        return {"processed": processed}
    except Exception as e:
        logger.error(f"Outbox WhatsApp processing failed: {e}")
        return {"error": str(e)}


@celery_app.task
def retry_failed_outbox():
    try:
        from app.services.communications.workers.retry_worker import RetryWorker
        worker = RetryWorker()
        processed = worker.run_once(batch_size=30)
        return {"retried": processed}
    except Exception as e:
        logger.error(f"Outbox retry processing failed: {e}")
        return {"error": str(e)}


@celery_app.task
def process_tracking_events():
    try:
        from app.services.communications.workers.analytics_worker import AnalyticsWorker
        worker = AnalyticsWorker()
        processed = worker.run_once()
        return {"processed": processed}
    except Exception as e:
        logger.error(f"Tracking event processing failed: {e}")
        return {"error": str(e)}


@celery_app.task
def cleanup_outbox():
    try:
        from app.services.communications.workers.cleanup_worker import CleanupWorker
        worker = CleanupWorker()
        deleted = worker.run_once()
        return {"deleted": deleted}
    except Exception as e:
        logger.error(f"Outbox cleanup failed: {e}")
        return {"error": str(e)}
