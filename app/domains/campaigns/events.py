"""Campaign domain events."""
def build_campaign_created_event(campaign_id: str, tenant_id: str, name: str, campaign_type: str) -> dict:
    return {"campaign_id": campaign_id, "tenant_id": tenant_id, "name": name, "type": campaign_type}


def build_campaign_launched_event(campaign_id: str, tenant_id: str, total_recipients: int) -> dict:
    return {"campaign_id": campaign_id, "tenant_id": tenant_id, "total_recipients": total_recipients}


def build_campaign_message_sent_event(message_id: str, campaign_id: str, lead_id: str, channel: str, status: str) -> dict:
    return {"message_id": message_id, "campaign_id": campaign_id, "lead_id": lead_id, "channel": channel, "status": status}
