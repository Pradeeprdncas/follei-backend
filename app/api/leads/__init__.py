from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func
from uuid import uuid4

from app.database.session import get_db
from app.models.leads.lead import Lead
from app.schemas.lead import LeadResponse, LeadListResponse, CreateLeadRequest
from app.domains.lead_import.utils import (
    normalize_email, normalize_phone, normalize_website, split_full_name,
)
from app.domains.lead_import.scoring import calculate_quality_score

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
def create_lead(payload: CreateLeadRequest):
    """Create a single lead manually. Runs normalization, enrichment, and quality scoring."""
    db = next(get_db())
    try:
        email = normalize_email(payload.email)
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")

        phone = normalize_phone(payload.phone or "")
        website = normalize_website(payload.website or "")

        first_name = payload.first_name
        last_name = payload.last_name
        if not first_name and payload.full_name:
            first_name, last_name = split_full_name(payload.full_name)

        lead = Lead(
            id=uuid4(),
            tenant_id=payload.tenant_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            company=payload.company,
            phone=int("".join(c for c in phone if c.isdigit())[:15]) if phone else 0,
            status="new",
        )
        db.add(lead)
        db.flush()

        # Run enrichment & quality scoring
        lead_data = {
            "first_name": first_name,
            "last_name": last_name,
            "company": payload.company,
            "email": email,
            "phone": phone,
            "website": website,
        }
        from app.domains.lead_import.service import _apply_batch_corrections
        lead_data = _apply_batch_corrections([lead_data])[0]
        quality = calculate_quality_score(lead_data)

        db.commit()

        return LeadResponse(
            id=str(lead.id),
            tenant_id=str(lead.tenant_id),
            public_id=lead.public_id or "",
            email=lead.email or "",
            first_name=lead.first_name,
            last_name=lead.last_name,
            company=lead.company,
            phone=str(lead.phone) if lead.phone else None,
            status=lead.status,
            current_temperature=lead.current_temperature,
            current_score=lead.current_score,
            created_at=lead.created_at,
        )
    finally:
        db.close()


@router.get("", response_model=LeadListResponse)
def list_leads(
    tenant_id: str | None = Query(None),
    status: str | None = Query(None),
    email: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    """List leads with optional filtering and pagination."""
    db = next(get_db())
    try:
        query = select(Lead)
        if tenant_id:
            query = query.where(Lead.tenant_id == tenant_id)
        if status:
            query = query.where(Lead.status == status)
        if email:
            query = query.where(Lead.email.ilike(f"%{email}%"))
        if search:
            pattern = f"%{search}%"
            query = query.where(
                Lead.first_name.ilike(pattern)
                | Lead.last_name.ilike(pattern)
                | Lead.email.ilike(pattern)
                | Lead.company.ilike(pattern)
            )
        count_query = select(func.count()).select_from(query.subquery())
        total = db.execute(count_query).scalar() or 0
        query = query.order_by(Lead.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = db.execute(query)
        leads = result.scalars().all()
        items = [
            LeadResponse(
                id=str(l.id),
                tenant_id=str(l.tenant_id),
                public_id=l.public_id or "",
                email=l.email or "",
                first_name=l.first_name,
                last_name=l.last_name,
                company=l.company,
                phone=str(l.phone) if l.phone else None,
                status=l.status,
                current_temperature=l.current_temperature,
                current_score=l.current_score,
                created_at=l.created_at,
            )
            for l in leads
        ]
        return LeadListResponse(items=items, total=total, page=page, page_size=page_size)
    finally:
        db.close()


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: str):
    """Get a single lead by ID."""
    db = next(get_db())
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        return LeadResponse(
            id=str(lead.id),
            tenant_id=str(lead.tenant_id),
            public_id=lead.public_id or "",
            email=lead.email or "",
            first_name=lead.first_name,
            last_name=lead.last_name,
            company=lead.company,
            phone=str(lead.phone) if lead.phone else None,
            status=lead.status,
            current_temperature=lead.current_temperature,
            current_score=lead.current_score,
            created_at=lead.created_at,
        )
    finally:
        db.close()
