"""Campaign router — delegates all operations to CampaignService."""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Response, status, Depends
from fastapi.responses import RedirectResponse, Response as FastAPIResponse
from urllib.parse import urlparse

from app.database.session import get_db
from app.models.campaigns import DeliveryStatus
from app.schemas.campaign import (
    CampaignCreateRequest, CampaignUpdateRequest,
    CampaignResponse, CampaignListResponse, CampaignStatsResponse,
    CampaignInboundEmailResponse, CampaignInboundEmailListResponse,
    CampaignInboundWebhookResponse, CampaignMetricCreate, CampaignMetricResponse,
)
from app.services.campaigns.service import CampaignService

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])
metrics_router = APIRouter(prefix="/campaign-metrics", tags=["Campaigns"])
inbound_router = APIRouter(prefix="/email/inbound", tags=["Campaigns"])

# Whitelist of allowed redirect domains for click tracking
_ALLOWED_REDIRECT_DOMAINS: set[str] | None = None


def _svc(db=Depends(get_db)) -> CampaignService:
    return CampaignService(db)


def _validate_redirect_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Invalid URL scheme")
    if _ALLOWED_REDIRECT_DOMAINS is not None:
        host = parsed.hostname or ""
        if not any(host == d or host.endswith("." + d) for d in _ALLOWED_REDIRECT_DOMAINS):
            raise HTTPException(status_code=400, detail="Redirect domain not allowed")
    return url


# ── CRUD ─────────────────────────────────────────────────────────────

@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
def create_campaign(payload: CampaignCreateRequest, svc: CampaignService = Depends(_svc)) -> CampaignResponse:
    return svc.create(payload)


@router.get("", response_model=CampaignListResponse)
def list_campaigns(
    tenant_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    type_filter: str | None = Query(default=None, alias="type"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    svc: CampaignService = Depends(_svc),
) -> CampaignListResponse:
    return svc.list(tenant_id, status_filter, type_filter, page, page_size)


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: str, svc: CampaignService = Depends(_svc)) -> CampaignResponse:
    return svc.get_response(campaign_id)


@router.put("/{campaign_id}", response_model=CampaignResponse)
def update_campaign(campaign_id: str, payload: CampaignUpdateRequest,
                    svc: CampaignService = Depends(_svc)) -> CampaignResponse:
    return svc.update(campaign_id, payload)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_id: str, svc: CampaignService = Depends(_svc)):
    svc.delete(campaign_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Lifecycle ─────────────────────────────────────────────────────────

@router.post("/{campaign_id}/start", response_model=dict)
async def start_campaign(campaign_id: str, svc: CampaignService = Depends(_svc)):
    return await svc.start(campaign_id)


@router.post("/{campaign_id}/schedule", response_model=CampaignResponse)
def schedule_campaign(campaign_id: str, svc: CampaignService = Depends(_svc)) -> CampaignResponse:
    return svc.schedule(campaign_id)


@router.post("/{campaign_id}/pause", response_model=CampaignResponse)
def pause_campaign(campaign_id: str, svc: CampaignService = Depends(_svc)) -> CampaignResponse:
    return svc.pause(campaign_id)


@router.post("/{campaign_id}/cancel", response_model=CampaignResponse)
def cancel_campaign(campaign_id: str, svc: CampaignService = Depends(_svc)) -> CampaignResponse:
    return svc.cancel(campaign_id)


# ── Stats / Analytics ────────────────────────────────────────────────

@router.get("/{campaign_id}/stats", response_model=CampaignStatsResponse)
def get_campaign_stats(campaign_id: str, svc: CampaignService = Depends(_svc)) -> CampaignStatsResponse:
    return svc.get_stats(campaign_id)


@router.get("/{campaign_id}/analytics", response_model=dict)
def get_campaign_analytics(campaign_id: str, svc: CampaignService = Depends(_svc)) -> dict:
    return svc.get_analytics(campaign_id)


# ── Lead Management ──────────────────────────────────────────────────

@router.post("/{campaign_id}/leads/{lead_id}", status_code=201)
def add_lead_to_campaign(campaign_id: str, lead_id: str,
                         svc: CampaignService = Depends(_svc)) -> dict:
    return svc.add_lead(campaign_id, lead_id)


@router.delete("/{campaign_id}/leads/{lead_id}", status_code=204)
def remove_lead_from_campaign(campaign_id: str, lead_id: str,
                              svc: CampaignService = Depends(_svc)):
    svc.remove_lead(campaign_id, lead_id)
    return Response(status_code=204)


@router.get("/{campaign_id}/leads", response_model=dict)
def list_campaign_leads(campaign_id: str, svc: CampaignService = Depends(_svc)) -> dict:
    return svc.list_leads(campaign_id)


# ── Tracking ──────────────────────────────────────────────────────────

@router.get("/{campaign_id}/track/open")
def track_open(campaign_id: str, message_id: str = Query(...),
               tenant_id: str = Query(...),
               svc: CampaignService = Depends(_svc)):
    svc.track_open(message_id, campaign_id, tenant_id)
    return FastAPIResponse(content=_TRANSPARENT_PIXEL, media_type="image/gif")


@router.get("/{campaign_id}/track/click")
def track_click(campaign_id: str, message_id: str = Query(...),
                url: str = Query(...),
                tenant_id: str = Query(...),
                svc: CampaignService = Depends(_svc)):
    svc.track_click(message_id, campaign_id, tenant_id)
    safe_url = _validate_redirect_url(url)
    return RedirectResponse(url=safe_url)


@router.post("/{campaign_id}/track/delivery")
def track_delivery(campaign_id: str, message_id: str = Query(...),
                   status: str = Query(...),
                   tenant_id: str = Query(...),
                   provider_id: str | None = Query(default=None),
                   error: str | None = Query(default=None),
                   svc: CampaignService = Depends(_svc)):
    try:
        delivery_status = DeliveryStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid delivery status: {status}")
    svc.track_delivery(message_id, campaign_id, tenant_id, delivery_status, provider_id, error)
    return {"received": True}


@router.post("/{campaign_id}/track/bounce")
def track_bounce(campaign_id: str, message_id: str = Query(...),
                 tenant_id: str = Query(...),
                 error: str | None = Query(default=None),
                 svc: CampaignService = Depends(_svc)):
    svc.track_bounce(message_id, campaign_id, tenant_id, error)
    return {"received": True}


# ── Inbound Email Webhooks ───────────────────────────────────────────

@inbound_router.post("/brevo", response_model=CampaignInboundWebhookResponse)
def receive_brevo_inbound_email(
    payload: dict,
    tenant_id: str | None = None,
    campaign_id: str | None = None,
    lead_id: str | None = None,
    svc: CampaignService = Depends(_svc),
) -> CampaignInboundWebhookResponse:
    from_email = _first_text(payload, ["from", "From", "sender", "Sender", "email", "from_email"])
    to_email = _first_text(payload, ["to", "To", "recipient", "recipients", "to_email"])
    subject = _first_text(payload, ["subject", "Subject"])
    body_text = _first_text(payload, ["text", "Text", "body", "Body", "html", "Html", "htmlContent", "textContent"])
    event_type = _first_text(payload, ["event", "eventType", "type"]) or "inbound"

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    tenant_id = tenant_id or metadata.get("tenant_id")
    campaign_id = campaign_id or metadata.get("campaign_id")
    lead_id = lead_id or metadata.get("lead_id")

    tenant_id, campaign_id, lead_id = svc.resolve_inbound_context(
        from_email, tenant_id, campaign_id, lead_id)
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Could not resolve tenant_id from webhook payload")

    inbound = svc.create_inbound_email(
        tenant_id=tenant_id, campaign_id=campaign_id, lead_id=lead_id,
        from_email=from_email, to_email=to_email, subject=subject,
        body=body_text, provider="brevo", event_type=event_type,
        raw_payload=payload,
    )

    if campaign_id:
        svc.track_delivery(str(inbound.id), DeliveryStatus.REPLIED)

    inbound_resp = CampaignInboundEmailResponse(
        id=str(inbound.id), tenant_id=tenant_id, campaign_id=campaign_id,
        lead_id=lead_id, from_email=from_email, to_email=to_email,
        subject=subject, body=body_text, provider="brevo",
        event_type=event_type, raw_payload=payload,
        received_at=inbound.received_at.isoformat() if inbound.received_at else _now(),
    )
    return CampaignInboundWebhookResponse(received=True, inbound_email=inbound_resp)


@inbound_router.get("", response_model=CampaignInboundEmailListResponse)
def list_inbound_emails(
    tenant_id: str | None = None, campaign_id: str | None = None,
    lead_id: str | None = None,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
    svc: CampaignService = Depends(_svc),
) -> CampaignInboundEmailListResponse:
    items, total = svc.list_inbound_emails(tenant_id, campaign_id, lead_id, page, page_size)
    resp_items = [
        CampaignInboundEmailResponse(
            id=str(i.id), tenant_id=str(i.tenant_id),
            campaign_id=str(i.campaign_id) if i.campaign_id else None,
            lead_id=str(i.lead_id) if i.lead_id else None,
            from_email=i.from_email, to_email=i.to_email,
            subject=i.subject, body=i.body, provider=i.provider,
            event_type=i.event_type, raw_payload=i.raw_payload or {},
            received_at=i.received_at.isoformat() if i.received_at else _now(),
        ) for i in items
    ]
    return CampaignInboundEmailListResponse(items=resp_items, total=total, page=page, page_size=page_size)


# ── Campaign Metrics ─────────────────────────────────────────────────

@metrics_router.post("", response_model=CampaignMetricResponse, status_code=status.HTTP_201_CREATED)
def create_metric(payload: CampaignMetricCreate, svc: CampaignService = Depends(_svc)) -> CampaignMetricResponse:
    metric = svc.create_metric(
        tenant_id=payload.tenant_id, campaign_id=payload.campaign_id,
        metric_type=payload.metric_type, value=payload.value,
        metadata_=payload.metadata_,
    )
    return CampaignMetricResponse(
        id=str(metric.id), campaign_id=str(metric.campaign_id),
        metric_type=metric.metric_type, value=metric.value,
        metadata_=metric.metadata_, tenant_id=str(metric.tenant_id),
        recorded_at=metric.recorded_at,
    )


@metrics_router.get("", response_model=dict)
def list_metrics(
    campaign_id: str | None = None, metric_type: str | None = None,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
    svc: CampaignService = Depends(_svc),
) -> dict:
    items, total = svc.list_metrics(campaign_id, metric_type, page, page_size)
    resp_items = [
        CampaignMetricResponse(
            id=str(m.id), campaign_id=str(m.campaign_id),
            metric_type=m.metric_type, value=m.value,
            metadata_=m.metadata_, tenant_id=str(m.tenant_id),
            recorded_at=m.recorded_at,
        ) for m in items
    ]
    return {"items": resp_items, "total": total, "page": page, "page_size": page_size}


@metrics_router.get("/{metric_id}", response_model=CampaignMetricResponse)
def get_metric(metric_id: str, svc: CampaignService = Depends(_svc)) -> CampaignMetricResponse:
    metric = svc.get_metric(metric_id)
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")
    return CampaignMetricResponse(
        id=str(metric.id), campaign_id=str(metric.campaign_id),
        metric_type=metric.metric_type, value=metric.value,
        metadata_=metric.metadata_, tenant_id=str(metric.tenant_id),
        recorded_at=metric.recorded_at,
    )


@metrics_router.delete("/{metric_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_metric(metric_id: str, svc: CampaignService = Depends(_svc)) -> Response:
    if not svc.delete_metric(metric_id):
        raise HTTPException(status_code=404, detail="Metric not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Helpers ──────────────────────────────────────────────────────────

_TRANSPARENT_PIXEL = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00"
    b"\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00"
    b"\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00"
    b"\x00\x02\x02\x44\x01\x00\x3b"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first_text(payload: dict, keys: list[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            nested = value.get("email") or value.get("address") or value.get("Email")
            if isinstance(nested, str) and nested:
                return nested
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str) and first:
                return first
            if isinstance(first, dict):
                nested = first.get("email") or first.get("address") or first.get("Email")
                if isinstance(nested, str) and nested:
                    return nested
    return None
