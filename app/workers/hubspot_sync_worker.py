"""Asynchronous canonical HubSpot sync worker."""
from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID

from app.config.database import SessionLocal
from app.config.kafka import ensure_topics, get_consumer
from app.config.settings import get_settings
from app.models.crm import CRMSyncRun, TenantCRMConnection
from app.models.knowledge.document import KnowledgeSource
from app.models.knowledge.ingestion import IngestionRun, SourceIngestionJob
from app.services.crm.sync import sync_hubspot
from app.services.integrations.hubspot_oauth import HubSpotOAuthService


_settings = get_settings()


async def process_hubspot_job(data: dict) -> None:
    db = SessionLocal()
    tenant_id = UUID(data["tenant_id"])
    connection = db.query(TenantCRMConnection).filter(TenantCRMConnection.id == UUID(data["connection_id"]), TenantCRMConnection.tenant_id == tenant_id).first()
    crm_run = db.query(CRMSyncRun).filter(CRMSyncRun.id == UUID(data["crm_run_id"]), CRMSyncRun.tenant_id == tenant_id).first()
    ingestion_run = db.query(IngestionRun).filter(IngestionRun.id == UUID(data["ingestion_run_id"]), IngestionRun.tenant_id == tenant_id).first()
    ingestion_job = db.query(SourceIngestionJob).filter(SourceIngestionJob.id == UUID(data["ingestion_job_id"]), SourceIngestionJob.tenant_id == tenant_id).first()
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == UUID(data["source_id"]), KnowledgeSource.tenant_id == tenant_id).first()
    if not all((connection, crm_run, ingestion_run, ingestion_job, source)):
        db.close(); raise ValueError("Unknown or cross-tenant HubSpot sync job")
    try:
        ingestion_run.status = ingestion_job.status = source.status = "running"
        ingestion_job.attempt += 1; ingestion_run.started_at = datetime.utcnow(); db.commit()
        await HubSpotOAuthService().valid_access_token(db, connection)
        await sync_hubspot(db, tenant_id=tenant_id, connection=connection, resources=list(data["resources"]), page_size=int(data["page_size"]), max_pages_per_resource=int(data["max_pages_per_resource"]), project_now=bool(data["project_now"]), run=crm_run)
        ingestion_job.status = "completed"; ingestion_run.status = "completed"; source.status = "active"
        ingestion_run.document_count = sum((crm_run.object_counts or {}).values()); ingestion_run.completed_at = datetime.utcnow(); db.commit()
    except Exception as exc:
        ingestion_job.status = ingestion_run.status = source.status = "failed"
        ingestion_job.last_error = ingestion_run.error = str(exc)[:4000]
        ingestion_run.completed_at = datetime.utcnow(); db.commit(); raise
    finally:
        db.close()


class HubSpotSyncWorker:
    def run(self):
        ensure_topics(); consumer = get_consumer(_settings.KAFKA_TOPIC_CRM_SYNC, "follei-hubspot-sync")
        try:
            for message in consumer:
                try: asyncio.run(process_hubspot_job(message.value))
                finally: consumer.commit()
        finally: consumer.close()


if __name__ == "__main__":
    HubSpotSyncWorker().run()
