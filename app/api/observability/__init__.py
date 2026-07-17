"""Observability router — delegates to ObservabilityService."""
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.observability_service import ObservabilityService
from app.auth.dependencies import get_current_user
from app.models.tenancy import User

router = APIRouter(prefix="/observability", tags=["Observability"])


class EventIn(BaseModel):
    event_type: str
    tenant_id: UUID
    user_id: Optional[UUID] = None
    properties: dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None


class RetrievalLogIn(BaseModel):
    query: str
    tenant_id: UUID
    agent_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None
    results_count: int = 0
    latency_ms: Optional[int] = None
    tokens_used: int = 0
    model: Optional[str] = None
    timestamp: Optional[datetime] = None


class EvaluationIn(BaseModel):
    query: str
    expected_answer: Optional[str] = None
    actual_answer: Optional[str] = None
    retrieved_chunks: list[UUID] = Field(default_factory=list)
    relevance_score: Optional[float] = None
    hallucination_detected: bool = False
    confidence: Optional[float] = None
    evaluator: Optional[str] = None
    notes: Optional[str] = None


def _svc(db: Session = Depends(get_db)) -> ObservabilityService:
    return ObservabilityService(db)


def _ensure_tenant(user: User, tenant_id: UUID) -> None:
    from fastapi import HTTPException
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")


@router.post("/events", status_code=201)
def create_event(payload: EventIn, user: User = Depends(get_current_user),
                 svc: ObservabilityService = Depends(_svc)):
    _ensure_tenant(user, payload.tenant_id)
    event = svc.create_event(
        tenant_id=user.tenant_id, event_type=payload.event_type,
        user_id=payload.user_id, properties=payload.properties,
        timestamp=payload.timestamp,
    )
    return {"id": event.id, "event_type": event.event_type, "tenant_id": event.tenant_id,
            "properties": event.payload, "created_at": event.created_at}


@router.get("/events")
def list_events(
    tenant_id: Optional[UUID] = None, event_type: Optional[str] = None,
    from_date: Optional[date] = Query(default=None, alias="from"),
    to_date: Optional[date] = Query(default=None, alias="to"),
    user: User = Depends(get_current_user), svc: ObservabilityService = Depends(_svc),
):
    tid = tenant_id or user.tenant_id
    if tenant_id:
        _ensure_tenant(user, tid)
    events = svc.list_events(tid, event_type, from_date, to_date)
    return {
        "items": [
            {"id": e.id, "event_type": e.event_type, "properties": e.payload, "created_at": e.created_at}
            for e in events
        ]
    }


@router.get("/daily")
def daily_metrics(
    tenant_id: Optional[UUID] = None, metric_date: date = Query(default_factory=date.today, alias="date"),
    user: User = Depends(get_current_user), svc: ObservabilityService = Depends(_svc),
):
    tid = tenant_id or user.tenant_id
    if tenant_id:
        _ensure_tenant(user, tid)
    return svc.get_daily_metrics(tid, metric_date)


@router.get("/monthly")
def monthly_metrics(
    tenant_id: Optional[UUID] = None, year: int = 2026, month: int = 6,
    user: User = Depends(get_current_user), svc: ObservabilityService = Depends(_svc),
):
    tid = tenant_id or user.tenant_id
    if tenant_id:
        _ensure_tenant(user, tid)
    return svc.get_monthly_metrics(tid, year, month)


@router.post("/retrieval-logs", status_code=201)
def create_retrieval_log(
    payload: RetrievalLogIn, user: User = Depends(get_current_user),
    svc: ObservabilityService = Depends(_svc),
):
    _ensure_tenant(user, payload.tenant_id)
    log = svc.create_retrieval_log(
        tenant_id=user.tenant_id, query=payload.query,
        latency_ms=payload.latency_ms, timestamp=payload.timestamp,
        agent_id=str(payload.agent_id) if payload.agent_id else None,
        conversation_id=str(payload.conversation_id) if payload.conversation_id else None,
        results_count=payload.results_count, tokens_used=payload.tokens_used,
        model=payload.model,
    )
    return {"id": log.id, "query": log.query, "latency_ms": log.latency_ms, "created_at": log.created_at}


@router.get("/retrieval-logs")
def list_retrieval_logs(
    tenant_id: Optional[UUID] = None, from_date: Optional[date] = Query(default=None, alias="from"),
    user: User = Depends(get_current_user), svc: ObservabilityService = Depends(_svc),
):
    tid = tenant_id or user.tenant_id
    if tenant_id:
        _ensure_tenant(user, tid)
    logs = svc.list_retrieval_logs(tid, from_date)
    return {
        "items": [
            {"id": l.id, "query": l.query, "latency_ms": l.latency_ms, "created_at": l.created_at}
            for l in logs
        ]
    }


@router.post("/evaluations", status_code=201)
def create_evaluation(
    payload: EvaluationIn, user: User = Depends(get_current_user),
    svc: ObservabilityService = Depends(_svc),
):
    eval_ = svc.create_evaluation(
        tenant_id=user.tenant_id, evaluator=payload.evaluator,
        relevance_score=payload.relevance_score,
        query=payload.query, expected_answer=payload.expected_answer,
        actual_answer=payload.actual_answer, hallucination_detected=payload.hallucination_detected,
        confidence=payload.confidence, notes=payload.notes,
    )
    return {"id": eval_.id}


@router.get("/evaluations")
def list_evaluations(
    user: User = Depends(get_current_user), svc: ObservabilityService = Depends(_svc),
):
    evals = svc.list_evaluations(user.tenant_id)
    relevance = [float(e.score) for e in evals if e.score is not None]
    confidence = [float((e.result or {}).get("confidence")) for e in evals if (e.result or {}).get("confidence") is not None]
    hallucinations = [e for e in evals if (e.result or {}).get("hallucination_detected")]
    return {
        "items": [
            {"id": e.id, "relevance_score": float(e.score or 0),
             "hallucination_detected": (e.result or {}).get("hallucination_detected", False)}
            for e in evals
        ],
        "avg_relevance": sum(relevance) / len(relevance) if relevance else 0,
        "avg_confidence": sum(confidence) / len(confidence) if confidence else 0,
        "hallucination_rate": len(hallucinations) / len(evals) if evals else 0,
    }


@router.get("/model-usage")
def model_usage(
    user: User = Depends(get_current_user), svc: ObservabilityService = Depends(_svc),
):
    return {"models": svc.get_model_usage(user.tenant_id)}


@router.get("/dashboard")
def dashboard():
    return {"period": "current", "conversations": {"total": 0, "active": 0, "resolved": 0},
            "leads": {"total": 0, "qualified": 0, "converted": 0},
            "customers": {"total": 0, "active": 0, "at_risk": 0},
            "revenue": {"mrr": 0, "new": 0, "expansion": 0, "churn": 0},
            "ai": {"total_requests": 0, "avg_confidence": 0, "avg_latency_ms": 0, "cost_usd": 0}}
