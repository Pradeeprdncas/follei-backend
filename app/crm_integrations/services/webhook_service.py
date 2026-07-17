from typing import Any


class WebhookService:
    async def handle_webhook(self, provider: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        signature = headers.get("x-hubspot-signature") or headers.get("x-zoho-webhook-signature") or headers.get("x-signature")
        if not signature:
            return {"provider": provider, "status": "rejected", "message": "Webhook signature is required before processing provider data."}
        event_type = payload.get("event") or payload.get("type")
        if not event_type:
            return {"provider": provider, "status": "rejected", "message": "Webhook event type is required."}
        return {"provider": provider, "status": "received", "event_type": event_type}
