"""Observability service."""
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository
from app.models.domain import AnalyticsDaily, AnalyticsMonthly, EvaluationResult, Event, ModelUsage, RetrievalLog


class ObservabilityService:
    def __init__(self, db: Session):
        self.db = db
        self.event_repo = BaseRepository(db, Event)
        self.retrieval_log_repo = BaseRepository(db, RetrievalLog)
        self.evaluation_repo = BaseRepository(db, EvaluationResult)

    def create_event(self, tenant_id: UUID, event_type: str,
                     user_id: UUID | None = None, properties: dict | None = None,
                     timestamp: datetime | None = None) -> Event:
        event = Event(
            tenant_id=tenant_id, event_type=event_type,
            payload={"user_id": str(user_id) if user_id else None, **(properties or {})},
            created_at=timestamp or datetime.utcnow(),
        )
        return self.event_repo.create(event)

    def list_events(self, tenant_id: UUID, event_type: str | None = None,
                    from_date: date | None = None, to_date: date | None = None) -> list[Event]:
        q = self.db.query(Event).filter(Event.tenant_id == tenant_id)
        if event_type:
            q = q.filter(Event.event_type == event_type)
        if from_date:
            q = q.filter(Event.created_at >= datetime.combine(from_date, datetime.min.time()))
        if to_date:
            q = q.filter(Event.created_at <= datetime.combine(to_date, datetime.max.time()))
        return q.order_by(Event.created_at.desc()).limit(100).all()

    def get_daily_metrics(self, tenant_id: UUID, metric_date: date) -> dict:
        rows = self.db.query(AnalyticsDaily).filter(
            AnalyticsDaily.tenant_id == tenant_id,
            AnalyticsDaily.metric_date == metric_date,
        ).all()
        metrics = {r.metric_name: float(r.metric_value) for r in rows}
        return {
            "date": str(metric_date), "tenant_id": tenant_id,
            "conversations": metrics.get("conversations", 0),
            "messages": metrics.get("messages", 0),
            "leads_created": metrics.get("leads_created", 0),
            "leads_converted": metrics.get("leads_converted", 0),
            "api_calls": metrics.get("api_calls", 0),
            "tokens_used": metrics.get("tokens_used", 0),
            "avg_response_time_ms": metrics.get("avg_response_time_ms", 0),
            "cost_usd": metrics.get("cost_usd", 0),
        }

    def get_monthly_metrics(self, tenant_id: UUID, year: int, month: int) -> dict:
        metric_month = date(year, month, 1)
        rows = self.db.query(AnalyticsMonthly).filter(
            AnalyticsMonthly.tenant_id == tenant_id,
            AnalyticsMonthly.metric_month == metric_month,
        ).all()
        metrics = {r.metric_name: float(r.metric_value) for r in rows}
        return {"tenant_id": tenant_id, "year": year, "month": month, "metrics": metrics}

    def create_retrieval_log(self, tenant_id: UUID, query: str, latency_ms: int | None = None,
                             timestamp: datetime | None = None, **kwargs) -> RetrievalLog:
        log = RetrievalLog(
            tenant_id=tenant_id, query=query, results=kwargs,
            scores=[], latency_ms=latency_ms,
            created_at=timestamp or datetime.utcnow(),
        )
        return self.retrieval_log_repo.create(log)

    def list_retrieval_logs(self, tenant_id: UUID, from_date: date | None = None) -> list[RetrievalLog]:
        q = self.db.query(RetrievalLog).filter(RetrievalLog.tenant_id == tenant_id)
        if from_date:
            q = q.filter(RetrievalLog.created_at >= datetime.combine(from_date, datetime.min.time()))
        return q.order_by(RetrievalLog.created_at.desc()).limit(100).all()

    def create_evaluation(self, tenant_id: UUID, evaluator: str | None = None,
                          relevance_score: float | None = None, **kwargs) -> EvaluationResult:
        eval_ = EvaluationResult(
            tenant_id=tenant_id, subject_type="rag",
            evaluator=evaluator, score=relevance_score,
            result=kwargs,
        )
        return self.evaluation_repo.create(eval_)

    def list_evaluations(self, tenant_id: UUID) -> dict:
        evals = self.db.query(EvaluationResult).filter(
            EvaluationResult.tenant_id == tenant_id
        ).order_by(EvaluationResult.created_at.desc()).all()
        return evals

    def get_model_usage(self, tenant_id: UUID) -> list[dict]:
        rows = self.db.query(
            ModelUsage.model,
            func.count(ModelUsage.id),
            func.sum(ModelUsage.prompt_tokens),
            func.sum(ModelUsage.completion_tokens),
            func.sum(ModelUsage.total_tokens),
            func.sum(ModelUsage.cost),
        ).filter(ModelUsage.tenant_id == tenant_id).group_by(ModelUsage.model).all()
        return [
            {
                "model": model, "requests": requests,
                "tokens_in": tokens_in or 0, "tokens_out": tokens_out or 0,
                "tokens": tokens or 0, "cost_usd": float(cost or 0),
            }
            for model, requests, tokens_in, tokens_out, tokens, cost in rows
        ]
