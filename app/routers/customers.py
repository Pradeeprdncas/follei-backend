from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.schemas.customer import (
    CreateCustomerRequest,
    CustomerContactListResponse,
    CustomerContactRequest,
    CustomerContactResponse,
    CustomerEventListResponse,
    CustomerEventRequest,
    CustomerEventResponse,
    CustomerListResponse,
    CustomerResponse,
    HealthScoreListResponse,
    HealthScoreRequest,
    HealthScoreResponse,
    RenewalListResponse,
    RenewalRequest,
    RenewalResponse,
    UpdateCustomerRequest,
    UpdateRenewalRequest,
)

router = APIRouter(prefix="/customers", tags=["Customers & Customer Success"])
renewals_router = APIRouter(prefix="/renewals", tags=["Customers & Customer Success"])

CUSTOMERS: dict[str, CustomerResponse] = {}
CONTACTS: dict[str, CustomerContactResponse] = {}
CUSTOMER_CONTACTS: dict[str, list[str]] = {}
HEALTH_SCORES: dict[str, HealthScoreResponse] = {}
CUSTOMER_HEALTH_SCORES: dict[str, list[str]] = {}
EVENTS: dict[str, CustomerEventResponse] = {}
CUSTOMER_EVENTS: dict[str, list[str]] = {}
RENEWALS: dict[str, RenewalResponse] = {}
CUSTOMER_RENEWALS: dict[str, list[str]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_customer_or_404(customer_id: str) -> CustomerResponse:
    customer = CUSTOMERS.get(customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CreateCustomerRequest) -> CustomerResponse:
    now = _now()
    customer_id = str(uuid4())
    customer = CustomerResponse(
        id=customer_id,
        name=payload.name,
        email=str(payload.email) if payload.email else None,
        phone=payload.phone,
        tenant_id=payload.tenant_id,
        status=payload.status,
        plan_id=payload.plan_id,
        mrr=payload.mrr,
        arr=payload.arr,
        industry=payload.industry,
        company_size=payload.company_size,
        billing_address=payload.billing_address,
        custom_fields=payload.custom_fields,
        health_score=0,
        churn_risk="unknown",
        expansion_score=0,
        contacts=[],
        conversations=[],
        events=[],
        created_at=now,
        updated_at=now,
    )
    CUSTOMERS[customer_id] = customer
    return customer


@router.get("", response_model=CustomerListResponse)
def list_customers(
    tenant_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    plan_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> CustomerListResponse:
    items = list(CUSTOMERS.values())
    if tenant_id is not None:
        items = [item for item in items if item.tenant_id == tenant_id]
    if status_filter is not None:
        items = [item for item in items if item.status == status_filter]
    if plan_id is not None:
        items = [item for item in items if item.plan_id == plan_id]

    total = len(items)
    start = (page - 1) * page_size
    return CustomerListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: str) -> CustomerResponse:
    return _get_customer_or_404(customer_id)


@router.patch("/{customer_id}", response_model=CustomerResponse)
def update_customer(customer_id: str, payload: UpdateCustomerRequest) -> CustomerResponse:
    customer = _get_customer_or_404(customer_id)
    data = payload.model_dump(exclude_unset=True)
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"])
    updated = customer.model_copy(update={**data, "updated_at": _now()})
    CUSTOMERS[customer_id] = updated
    return updated


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: str) -> Response:
    _get_customer_or_404(customer_id)
    CUSTOMERS.pop(customer_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get_renewal_or_404(renewal_id: str) -> RenewalResponse:
    renewal = RENEWALS.get(renewal_id)
    if renewal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Renewal not found")
    return renewal


@router.post("/{customer_id}/contacts", response_model=CustomerContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact(customer_id: str, payload: CustomerContactRequest) -> CustomerContactResponse:
    _get_customer_or_404(customer_id)
    contact_id = str(uuid4())
    contact = CustomerContactResponse(
        id=contact_id,
        customer_id=customer_id,
        email=str(payload.email) if payload.email else None,
        created_at=_now(),
        **payload.model_dump(exclude={"email"}),
    )
    CONTACTS[contact_id] = contact
    CUSTOMER_CONTACTS.setdefault(customer_id, []).append(contact_id)
    return contact


@router.get("/{customer_id}/contacts", response_model=CustomerContactListResponse)
def list_contacts(
    customer_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> CustomerContactListResponse:
    _get_customer_or_404(customer_id)
    items = [CONTACTS[item_id] for item_id in CUSTOMER_CONTACTS.get(customer_id, []) if item_id in CONTACTS]
    total = len(items)
    start = (page - 1) * page_size
    return CustomerContactListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@router.post("/{customer_id}/health-scores", response_model=HealthScoreResponse, status_code=status.HTTP_201_CREATED)
def create_health_score(customer_id: str, payload: HealthScoreRequest) -> HealthScoreResponse:
    customer = _get_customer_or_404(customer_id)
    score_value = 88 if payload.force_recalculate else max(customer.health_score, 75)
    score_id = str(uuid4())
    score = HealthScoreResponse(
        id=score_id,
        customer_id=customer_id,
        score=score_value,
        model=payload.model,
        factors={"usage": 30, "support": 20, "payment": 20, "engagement": 18},
        trend="up",
        metadata=payload.metadata,
        calculated_at=_now(),
    )
    HEALTH_SCORES[score_id] = score
    CUSTOMER_HEALTH_SCORES.setdefault(customer_id, []).append(score_id)
    CUSTOMERS[customer_id] = customer.model_copy(update={"health_score": score_value, "updated_at": _now()})
    return score


@router.get("/{customer_id}/health-scores", response_model=HealthScoreListResponse)
def list_health_scores(
    customer_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> HealthScoreListResponse:
    _get_customer_or_404(customer_id)
    items = [HEALTH_SCORES[item_id] for item_id in CUSTOMER_HEALTH_SCORES.get(customer_id, []) if item_id in HEALTH_SCORES]
    total = len(items)
    start = (page - 1) * page_size
    return HealthScoreListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@router.post("/{customer_id}/events", response_model=CustomerEventResponse, status_code=status.HTTP_201_CREATED)
def create_event(customer_id: str, payload: CustomerEventRequest) -> CustomerEventResponse:
    _get_customer_or_404(customer_id)
    event_id = str(uuid4())
    event = CustomerEventResponse(
        id=event_id,
        customer_id=customer_id,
        type=payload.type,
        feature=payload.feature,
        timestamp=(payload.timestamp.isoformat() if payload.timestamp else _now()),
        metadata=payload.metadata,
        created_at=_now(),
    )
    EVENTS[event_id] = event
    CUSTOMER_EVENTS.setdefault(customer_id, []).append(event_id)
    return event


@router.get("/{customer_id}/events", response_model=CustomerEventListResponse)
def list_events(
    customer_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> CustomerEventListResponse:
    _get_customer_or_404(customer_id)
    items = [EVENTS[item_id] for item_id in CUSTOMER_EVENTS.get(customer_id, []) if item_id in EVENTS]
    total = len(items)
    start = (page - 1) * page_size
    return CustomerEventListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@router.post("/{customer_id}/renewals", response_model=RenewalResponse, status_code=status.HTTP_201_CREATED)
def create_renewal(customer_id: str, payload: RenewalRequest) -> RenewalResponse:
    _get_customer_or_404(customer_id)
    now = _now()
    renewal_id = str(uuid4())
    renewal = RenewalResponse(
        id=renewal_id,
        customer_id=customer_id,
        status="upcoming",
        actual_value=None,
        closed_date=None,
        created_at=now,
        updated_at=now,
        **payload.model_dump(),
    )
    RENEWALS[renewal_id] = renewal
    CUSTOMER_RENEWALS.setdefault(customer_id, []).append(renewal_id)
    return renewal


@router.get("/{customer_id}/renewals", response_model=RenewalListResponse)
def list_renewals(
    customer_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> RenewalListResponse:
    _get_customer_or_404(customer_id)
    items = [RENEWALS[item_id] for item_id in CUSTOMER_RENEWALS.get(customer_id, []) if item_id in RENEWALS]
    total = len(items)
    start = (page - 1) * page_size
    return RenewalListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@renewals_router.patch("/{renewal_id}", response_model=RenewalResponse)
def update_renewal(renewal_id: str, payload: UpdateRenewalRequest) -> RenewalResponse:
    renewal = _get_renewal_or_404(renewal_id)
    updated = renewal.model_copy(update={**payload.model_dump(exclude_unset=True), "updated_at": _now()})
    RENEWALS[renewal_id] = updated
    return updated
