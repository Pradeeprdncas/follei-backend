from fastapi import APIRouter, Request
from app.crm_integrations.services.webhook_service import WebhookService


router = APIRouter(prefix="/api/crm/webhooks", tags=["CRM"])
webhook_service = WebhookService()


@router.post("/{provider}")
async def receive_webhook(provider: str, request: Request):
    payload = await request.json()
    result = await webhook_service.handle_webhook(provider=provider, payload=payload, headers=dict(request.headers))
    return result
