from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.domain import AnalyticsDaily, AnalyticsMonthly, EvaluationResult, Event, ModelUsage, RetrievalLog
from app.models.tenancy import User
from app.routers.auth import get_current_user

events_router = APIRouter(prefix="/events", tags=["Analytics & Observability"])
analytics_router = APIRouter(prefix="/analytics", tags=["Analytics & Observability"])
retrieval_router = APIRouter(prefix="/retrieval-logs", tags=["Analytics & Observability"])
evaluation_router = APIRouter(prefix="/evaluation-results", tags=["Analytics & Observability"])


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
    dense_results: int = 0
    bm25_results: int = 0
    rrf_results: int = 0
    reranked_results: int = 0
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


def _ensure_tenant(user: User, tenant_id: UUID) -> None:
    if tenant_id != user.tenant_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Tenant mismatch")


@events_router.post("", status_code=201)
def create_event(payload: EventIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_tenant(user, payload.tenant_id)
    event = Event(tenant_id=user.tenant_id, event_type=payload.event_type, payload={"user_id": str(payload.user_id) if payload.user_id else None, **payload.properties}, created_at=payload.timestamp or datetime.utcnow())
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"id": event.id, "event_type": event.event_type, "tenant_id": event.tenant_id, "properties": event.payload, "created_at": event.created_at}


@events_router.get("")
def list_events(
    tenant_id: Optional[UUID] = None,
    event_type: Optional[str] = None,
    from_date: Optional[date] = Query(default=None, alias="from"),
    to_date: Optional[date] = Query(default=None, alias="to"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if tenant_id:
        _ensure_tenant(user, tenant_id)
    query = db.query(Event).filter(Event.tenant_id == user.tenant_id)
    if event_type:
        query = query.filter(Event.event_type == event_type)
    if from_date:
        query = query.filter(Event.created_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        query = query.filter(Event.created_at <= datetime.combine(to_date, datetime.max.time()))
    events = query.order_by(Event.created_at.desc()).limit(100).all()
    return {"items": [{"id": item.id, "event_type": item.event_type, "properties": item.payload, "created_at": item.created_at} for item in events]}


def _metric_map(rows) -> dict[str, float]:
    return {row.metric_name: float(row.metric_value) for row in rows}


@analytics_router.get("/daily")
def daily_metrics(tenant_id: Optional[UUID] = None, metric_date: date = Query(default_factory=date.today, alias="date"), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if tenant_id:
        _ensure_tenant(user, tenant_id)
    metrics = _metric_map(db.query(AnalyticsDaily).filter(AnalyticsDaily.tenant_id == user.tenant_id, AnalyticsDaily.metric_date == metric_date).all())
    return {"date": str(metric_date), "tenant_id": user.tenant_id, "conversations": metrics.get("conversations", 0), "messages": metrics.get("messages", 0), "leads_created": metrics.get("leads_created", 0), "leads_converted": metrics.get("leads_converted", 0), "api_calls": metrics.get("api_calls", 0), "tokens_used": metrics.get("tokens_used", 0), "avg_response_time_ms": metrics.get("avg_response_time_ms", 0), "cost_usd": metrics.get("cost_usd", 0)}


@analytics_router.get("/monthly")
def monthly_metrics(tenant_id: Optional[UUID] = None, year: int = 2026, month: int = 6, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if tenant_id:
        _ensure_tenant(user, tenant_id)
    metric_month = date(year, month, 1)
    rows = db.query(AnalyticsMonthly).filter(AnalyticsMonthly.tenant_id == user.tenant_id, AnalyticsMonthly.metric_month == metric_month).all()
    return {"tenant_id": user.tenant_id, "year": year, "month": month, "metrics": _metric_map(rows)}


@analytics_router.get("/conversations")
def conversation_stats():
    return {"total_conversations": 0, "avg_duration_minutes": 0, "avg_messages_per_conversation": 0, "resolution_rate": 0, "escalation_rate": 0, "top_intents": [], "sentiment_distribution": {"positive": 0, "neutral": 0, "negative": 0}}


@analytics_router.get("/leads")
def lead_stats():
    return {"total_leads": 0, "by_status": {}, "conversion_rate": 0, "avg_time_to_qualify_days": 0, "avg_time_to_close_days": 0, "top_sources": []}


@analytics_router.get("/customers")
def customer_stats():
    return {"total_customers": 0, "active_customers": 0, "churned_this_month": 0, "avg_health_score": 0, "avg_mrr": 0, "expansion_revenue": 0, "contraction_revenue": 0}


@analytics_router.get("/agents/{agent_id}")
def agent_performance(agent_id: UUID):
    return {"agent_id": agent_id, "conversations_handled": 0, "messages_sent": 0, "avg_confidence": 0, "avg_response_time_ms": 0, "avg_tokens_per_message": 0, "customer_satisfaction": 0, "tool_usage": [], "rag_hit_rate": 0}


@retrieval_router.post("", status_code=201)
def create_retrieval_log(payload: RetrievalLogIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_tenant(user, payload.tenant_id)
    results = payload.model_dump()
    log = RetrievalLog(tenant_id=user.tenant_id, query=payload.query, results=results, scores=[], latency_ms=payload.latency_ms, created_at=payload.timestamp or datetime.utcnow())
    db.add(log)
    db.commit()
    db.refresh(log)
    return {"id": log.id, **results}


@retrieval_router.get("")
def list_retrieval_logs(tenant_id: Optional[UUID] = None, agent_id: Optional[UUID] = None, from_date: Optional[date] = Query(default=None, alias="from"), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if tenant_id:
        _ensure_tenant(user, tenant_id)
    query = db.query(RetrievalLog).filter(RetrievalLog.tenant_id == user.tenant_id)
    if from_date:
        query = query.filter(RetrievalLog.created_at >= datetime.combine(from_date, datetime.min.time()))
    logs = query.order_by(RetrievalLog.created_at.desc()).limit(100).all()
    return {"items": [{"id": item.id, "query": item.query, "latency_ms": item.latency_ms, "created_at": item.created_at, **(item.results or {})} for item in logs if not agent_id or (item.results or {}).get("agent_id") == str(agent_id)]}


@evaluation_router.post("", status_code=201)
def create_evaluation(payload: EvaluationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = payload.model_dump()
    evaluation = EvaluationResult(tenant_id=user.tenant_id, subject_type="rag", evaluator=payload.evaluator, score=payload.relevance_score, result=result)
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    return {"id": evaluation.id, **result}


@evaluation_router.get("")
def list_evaluations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    evaluations = db.query(EvaluationResult).filter(EvaluationResult.tenant_id == user.tenant_id).order_by(EvaluationResult.created_at.desc()).all()
    relevance = [float(item.score) for item in evaluations if item.score is not None]
    confidence = [float((item.result or {}).get("confidence")) for item in evaluations if (item.result or {}).get("confidence") is not None]
    hallucinations = [item for item in evaluations if (item.result or {}).get("hallucination_detected")]
    return {"items": [{"id": item.id, "relevance_score": float(item.score or 0), "hallucination_detected": (item.result or {}).get("hallucination_detected", False)} for item in evaluations], "avg_relevance": sum(relevance) / len(relevance) if relevance else 0, "avg_confidence": sum(confidence) / len(confidence) if confidence else 0, "hallucination_rate": len(hallucinations) / len(evaluations) if evaluations else 0}


@analytics_router.get("/model-usage")
def model_usage(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(ModelUsage.model, func.count(ModelUsage.id), func.sum(ModelUsage.prompt_tokens), func.sum(ModelUsage.completion_tokens), func.sum(ModelUsage.total_tokens), func.sum(ModelUsage.cost)).filter(ModelUsage.tenant_id == user.tenant_id).group_by(ModelUsage.model).all()
    return {"models": [{"model": model, "requests": requests, "tokens_in": tokens_in or 0, "tokens_out": tokens_out or 0, "tokens": tokens or 0, "cost_usd": float(cost or 0)} for model, requests, tokens_in, tokens_out, tokens, cost in rows]}


@analytics_router.get("/dashboard")
def dashboard():
    return {"period": "current", "conversations": {"total": 0, "active": 0, "resolved": 0}, "leads": {"total": 0, "qualified": 0, "converted": 0}, "customers": {"total": 0, "active": 0, "at_risk": 0}, "revenue": {"mrr": 0, "new": 0, "expansion": 0, "churn": 0}, "ai": {"total_requests": 0, "avg_confidence": 0, "avg_latency_ms": 0, "cost_usd": 0}}
