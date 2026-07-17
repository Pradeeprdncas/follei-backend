"""Analytics worker — consumes tracking events from Redis, updates DB.

Pulls from campaign:tracking and campaign:analytics streams and
writes aggregated stats to campaign_statistics or campaign counters.
"""
from loguru import logger

from app.services.communications.streams.redis_streams import (
    consume_tracking_events, ensure_consumer_group,
)
from app.repositories.campaign import CampaignRepository
from app.repositories.campaign_message import CampaignMessageRepository
from app.database.session import SessionLocal


class AnalyticsWorker:
    """Aggregates tracking events and updates campaign analytics."""

    def run_once(self) -> int:
        ensure_consumer_group()
        events = consume_tracking_events(batch_size=50)
        if not events:
            return 0

        db = SessionLocal()
        try:
            campaign_repo = CampaignRepository(db)
            msg_repo = CampaignMessageRepository(db)
            processed = 0

            for event in events:
                event_type = event.get("event_type", "")
                message_id = event.get("message_id", "")
                campaign_id = event.get("campaign_id", "")

                if not message_id or not campaign_id:
                    continue

                if event_type == "track.open":
                    msg_repo.track_open(message_id)
                    campaign_repo.increment_stat(campaign_id, "opened_count")
                elif event_type == "track.click":
                    msg_repo.track_click(message_id)
                    campaign_repo.increment_stat(campaign_id, "clicked_count")
                elif event_type == "track.delivery":
                    from app.models.campaigns import DeliveryStatus
                    status_val = event.get("data", {}).get("status", "delivered")
                    try:
                        status = DeliveryStatus(status_val)
                    except ValueError:
                        status = DeliveryStatus.DELIVERED
                    provider_id = event.get("data", {}).get("provider_id")
                    error = event.get("data", {}).get("error")
                    msg_repo.track_delivery(message_id, status, provider_id, error)
                    if status == DeliveryStatus.DELIVERED:
                        campaign_repo.increment_stat(campaign_id, "delivered_count")
                    elif status in (DeliveryStatus.FAILED, DeliveryStatus.BOUNCED):
                        campaign_repo.increment_stat(campaign_id, "failed_count")
                elif event_type == "track.bounce":
                    msg_repo.track_bounce(message_id)
                    campaign_repo.increment_stat(campaign_id, "bounced_count")
                elif event_type == "track.reply":
                    msg_repo.track_reply(message_id)
                    campaign_repo.increment_stat(campaign_id, "replied_count")

                processed += 1

            db.commit()
            return processed
        except Exception as e:
            logger.error(f"Analytics worker error: {e}")
            db.rollback()
            return 0
        finally:
            db.close()
