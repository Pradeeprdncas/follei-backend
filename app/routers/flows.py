from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.security import get_authenticated_tenant_id, get_authenticated_user_id
from app.models.flows import FlowDefinition, FlowEnrollment, FlowExecutionStep, FlowVersion, TenantWorkflowInstance, WorkflowApproval, WorkflowTemplate
from app.services.communications.email_connections import has_gmail_oauth_sender
from app.services.flows.service import (
    DEFAULT_SETTINGS,
    active_flow,
    coverage_for_flow,
    enroll_leads,
    ensure_default_flow,
    ensure_graph_node_ids,
    validate_graph,
    decide_approval,
    activate_tenant_workflow_runtime,
    activate_workflow_instance,
    apply_workflow_overrides,
    ensure_tenant_workflow_runtime,
    ensure_workflow_templates,
    record_node_event,
    record_documents,
)

router = APIRouter(prefix="/api/v1/flows", tags=["flow-builder"])
assets_router = APIRouter(prefix="/api/v1/communication-assets", tags=["communication-assets"])


class DraftUpdate(BaseModel):
    graph: dict
    settings: dict = Field(default_factory=dict)
    name: str | None = None


class EnrollmentRequest(BaseModel):
    mode: str = "all_eligible"
    lead_ids: list[UUID] = Field(default_factory=list)


class WorkflowOverrideRequest(BaseModel):
    overrides: dict = Field(default_factory=dict)


class WorkflowEventRequest(BaseModel):
    event: str = Field(..., min_length=1, max_length=100)
    payload: dict = Field(default_factory=dict)


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    metadata: dict = Field(default_factory=dict)


class DocumentSubmissionRequest(BaseModel):
    fields: dict = Field(default_factory=dict)


def _owned(db: Session, tenant_id: str, flow_id: str) -> FlowDefinition:
    try: flow_uuid = UUID(flow_id)
    except ValueError: raise HTTPException(404, "Flow not found")
    flow = db.query(FlowDefinition).filter_by(id=flow_uuid, tenant_id=tenant_id).first()
    if not flow: raise HTTPException(404, "Flow not found")
    return flow


def _version(db: Session, flow: FlowDefinition) -> FlowVersion:
    return db.query(FlowVersion).filter_by(flow_id=flow.id).order_by(FlowVersion.version.desc()).first()


def _payload(flow: FlowDefinition, version: FlowVersion) -> dict:
    return {"id": str(flow.id), "public_id": flow.public_id, "name": flow.name, "category": flow.category, "status": flow.status, "is_default": flow.is_default, "active_version_id": str(flow.active_version_id) if flow.active_version_id else None, "version": version.version, "version_status": version.status, "graph": version.graph, "settings": version.settings, "updated_at": flow.updated_at.isoformat()}


def _instance_payload(instance: TenantWorkflowInstance) -> dict:
    return {"id": str(instance.id), "public_id": instance.public_id, "template_id": str(instance.template_id), "flow_id": str(instance.flow_id), "parent_instance_id": str(instance.parent_instance_id) if instance.parent_instance_id else None, "parent_node_key": instance.parent_node_key, "name": instance.name, "status": instance.status, "overrides": instance.overrides, "created_at": instance.created_at.isoformat()}


@router.get("/templates")
def list_templates(db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    ensure_workflow_templates(db); db.commit()
    rows = db.query(WorkflowTemplate).filter_by(status="published").order_by(WorkflowTemplate.industry, WorkflowTemplate.slug, WorkflowTemplate.version).all()
    return [{"id": str(row.id), "public_id": row.public_id, "slug": row.slug, "industry": row.industry, "name": row.name, "version": row.version, "graph": row.graph, "node_contracts": row.node_contracts} for row in rows]


@router.get("/instances")
def list_workflow_instances(db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    instances = ensure_tenant_workflow_runtime(db, tenant_id)
    return [_instance_payload(row) for row in db.query(TenantWorkflowInstance).filter_by(tenant_id=tenant_id).order_by(TenantWorkflowInstance.created_at).all()]


@router.post("/instances/insurance", status_code=201)
def activate_insurance_workflow(db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    try: rows = activate_tenant_workflow_runtime(db, tenant_id, "insurance")
    except ValueError as exc: raise HTTPException(422, str(exc))
    return {key: _instance_payload(value) for key, value in rows.items()}


@router.patch("/instances/{instance_id}/overrides")
def save_workflow_overrides(instance_id: UUID, body: WorkflowOverrideRequest, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    instance = db.query(TenantWorkflowInstance).filter_by(id=instance_id, tenant_id=tenant_id).first()
    if not instance: raise HTTPException(404, "Workflow instance not found")
    try: version = apply_workflow_overrides(db, tenant_id, instance, body.overrides)
    except ValueError as exc: raise HTTPException(422, str(exc))
    return {**_instance_payload(instance), "draft_version": version.version, "version_status": version.status, "graph": version.graph}


@router.post("/instances/{instance_id}/activate")
def activate_instance(instance_id: UUID, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    instance = db.query(TenantWorkflowInstance).filter_by(id=instance_id, tenant_id=tenant_id).first()
    if not instance: raise HTTPException(404, "Workflow instance not found")
    try: version = activate_workflow_instance(db, tenant_id, instance)
    except ValueError as exc: raise HTTPException(422, str(exc))
    return {**_instance_payload(instance), "active_version": version.version, "version_status": version.status}


@router.post("/enrollments/{enrollment_id}/event")
def submit_workflow_event(enrollment_id: UUID, body: WorkflowEventRequest, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    try: row = record_node_event(db, tenant_id, enrollment_id, body.event, body.payload)
    except ValueError as exc: raise HTTPException(422, str(exc))
    return {"id": str(row.id), "status": row.status, "event": body.event, "payload": body.payload}


@router.post("/enrollments/{enrollment_id}/documents")
def submit_workflow_documents(enrollment_id: UUID, body: DocumentSubmissionRequest, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    try: row = record_documents(db, tenant_id, enrollment_id, body.fields)
    except ValueError as exc: raise HTTPException(422, str(exc))
    return {"id": str(row.id), "status": row.status, "accepted_fields": sorted(body.fields)}


@router.get("/approvals")
def list_workflow_approvals(db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    rows = db.query(WorkflowApproval).filter_by(tenant_id=tenant_id).order_by(WorkflowApproval.requested_at.desc()).all()
    return [{"id": str(row.id), "public_id": row.public_id, "enrollment_id": str(row.enrollment_id) if row.enrollment_id else None, "node_key": row.node_key, "action": row.action, "status": row.status, "requested_payload": row.requested_payload, "decision_metadata": row.decision_metadata} for row in rows]


@router.get("/enrollments/{enrollment_id}/audit")
def workflow_case_audit(enrollment_id: UUID, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    root = db.query(FlowEnrollment).filter_by(id=enrollment_id, tenant_id=tenant_id).first()
    if not root: raise HTTPException(404, "Workflow enrollment not found")
    enrollments, frontier = [root], [root.id]
    while frontier:
        children = db.query(FlowEnrollment).filter(FlowEnrollment.tenant_id == tenant_id, FlowEnrollment.parent_enrollment_id.in_(frontier)).all()
        enrollments.extend(children); frontier = [row.id for row in children]
    ids = [row.id for row in enrollments]
    steps = db.query(FlowExecutionStep).filter(FlowExecutionStep.tenant_id == tenant_id, FlowExecutionStep.enrollment_id.in_(ids)).order_by(FlowExecutionStep.created_at).all()
    approvals = db.query(WorkflowApproval).filter(WorkflowApproval.tenant_id == tenant_id, WorkflowApproval.enrollment_id.in_(ids)).order_by(WorkflowApproval.requested_at).all()
    versions = {row.flow_version_id: db.get(FlowVersion, row.flow_version_id) for row in enrollments}
    return {
        "case": {"root_enrollment_id": str(root.id), "public_id": root.public_id, "lead_id": str(root.lead_id), "status": root.status, "started_at": root.created_at.isoformat(), "completed_at": root.completed_at.isoformat() if root.completed_at else None},
        "enrollments": [{"id": str(row.id), "public_id": row.public_id, "parent_enrollment_id": str(row.parent_enrollment_id) if row.parent_enrollment_id else None, "parent_node_key": row.parent_node_key, "flow_id": str(row.flow_id), "flow_version_id": str(row.flow_version_id), "flow_version": versions[row.flow_version_id].version if versions[row.flow_version_id] else None, "status": row.status, "current_node_key": row.current_node_key, "stop_reason": row.stop_reason, "context": row.context} for row in enrollments],
        "steps": [{"id": str(row.id), "public_id": row.public_id, "enrollment_id": str(row.enrollment_id), "node_key": row.node_key, "node_id": row.node_id, "action_type": row.action_type, "status": row.status, "attempt": row.attempt, "output": row.output, "decision": row.decision, "verification": row.verification, "audit_metadata": row.audit_metadata, "created_at": row.created_at.isoformat()} for row in steps],
        "approvals": [{"id": str(row.id), "public_id": row.public_id, "enrollment_id": str(row.enrollment_id) if row.enrollment_id else None, "node_key": row.node_key, "action": row.action, "status": row.status, "task_id": str(row.task_id) if row.task_id else None, "assigned_to": str(row.assigned_to) if row.assigned_to else None, "sla_due_at": row.sla_due_at.isoformat() if row.sla_due_at else None, "notification_status": row.notification_status, "requested_at": row.requested_at.isoformat(), "decided_at": row.decided_at.isoformat() if row.decided_at else None, "decided_by": str(row.decided_by) if row.decided_by else None, "decision_metadata": row.decision_metadata} for row in approvals],
    }


@router.post("/approvals/{approval_id}/decision")
def decide_workflow_approval(approval_id: UUID, body: ApprovalDecisionRequest, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id), user_id: str = Depends(get_authenticated_user_id)):
    try: row = decide_approval(db, tenant_id, approval_id, body.approved, user_id, body.metadata)
    except ValueError as exc: raise HTTPException(422, str(exc))
    return {"id": str(row.id), "public_id": row.public_id, "status": row.status, "decided_at": row.decided_at.isoformat() if row.decided_at else None}


@router.get("/readiness")
def readiness(db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    flow = ensure_default_flow(db, tenant_id)
    version = _version(db, flow)
    errors = validate_graph(version.graph or {}, version.settings or {})
    email_ready = has_gmail_oauth_sender(db, tenant_id)
    return {"configured": not errors, "active": flow.status == "active", "flow_id": str(flow.id), "flow_status": flow.status, "email_ready": email_ready, "can_auto_enroll": flow.status == "active" and not errors and email_ready, "errors": errors, "reason": None if flow.status == "active" else "flow_not_active"}


@router.get("")
def list_flows(db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    ensure_default_flow(db, tenant_id)
    return [_payload(flow, _version(db, flow)) for flow in db.query(FlowDefinition).filter_by(tenant_id=tenant_id).order_by(FlowDefinition.created_at).all()]


@router.get("/{flow_id}")
def get_flow(flow_id: str, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    flow = _owned(db, tenant_id, flow_id)
    return _payload(flow, _version(db, flow))


@router.patch("/{flow_id}/draft")
def save_draft(flow_id: str, body: DraftUpdate, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    flow = _owned(db, tenant_id, flow_id)
    latest = _version(db, flow)
    if latest.status == "published":
        latest = FlowVersion(tenant_id=tenant_id, flow_id=flow.id, version=latest.version + 1, status="draft", graph=ensure_graph_node_ids(body.graph), settings={**DEFAULT_SETTINGS, **body.settings})
        db.add(latest)
    else:
        latest.graph, latest.settings = ensure_graph_node_ids(body.graph), {**DEFAULT_SETTINGS, **body.settings}
    if body.name: flow.name = body.name
    if flow.status == "active": flow.status = "draft"
    db.commit(); db.refresh(latest)
    return _payload(flow, latest)


@router.post("/{flow_id}/validate")
def validate(flow_id: str, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    flow = _owned(db, tenant_id, flow_id); version = _version(db, flow)
    errors = validate_graph(version.graph or {}, version.settings or {})
    return {"valid": not errors, "errors": errors, "email_ready": has_gmail_oauth_sender(db, tenant_id)}


@router.post("/{flow_id}/activate")
def activate(flow_id: str, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    flow = _owned(db, tenant_id, flow_id); version = _version(db, flow)
    errors = validate_graph(version.graph or {}, version.settings or {})
    if errors: raise HTTPException(422, {"message": "Flow validation failed", "errors": errors})
    if not has_gmail_oauth_sender(db, tenant_id):
        raise HTTPException(409, "Connect and enable a Gmail sender before activating an email flow.")
    db.query(FlowDefinition).filter(FlowDefinition.tenant_id == tenant_id, FlowDefinition.category == flow.category, FlowDefinition.id != flow.id, FlowDefinition.status == "active").update({"status": "paused"})
    version.status, version.published_at = "published", datetime.utcnow()
    flow.status, flow.active_version_id = "active", version.id
    db.commit()
    response = _payload(flow, version)
    if (version.settings or {}).get("auto_enroll_existing", False):
        from app.models.leads.lead import Lead
        ids = [row[0] for row in db.query(Lead.id).filter(Lead.tenant_id == tenant_id).all()]
        response["activation_enrollment"] = enroll_leads(db, tenant_id, ids, "activation_existing", pair=(flow, version))
    return response


@router.post("/{flow_id}/pause")
def pause(flow_id: str, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    flow = _owned(db, tenant_id, flow_id); flow.status = "paused"; db.commit()
    return {"id": str(flow.id), "status": flow.status}


@router.post("/{flow_id}/enroll-existing")
def enroll_existing(flow_id: str, body: EnrollmentRequest | None = None, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    from app.models.leads.lead import Lead
    body = body or EnrollmentRequest()
    flow = _owned(db, tenant_id, flow_id)
    if flow.status != "active": raise HTTPException(409, "Activate the flow first.")
    if body.mode == "selected":
        ids = list(body.lead_ids)
    elif body.mode == "all_eligible":
        ids = [row[0] for row in db.query(Lead.id).filter(Lead.tenant_id == tenant_id).all()]
    else:
        raise HTTPException(422, "mode must be all_eligible or selected")
    return enroll_leads(db, tenant_id, ids, "manual_existing")


@router.get("/{flow_id}/coverage")
def coverage(flow_id: str, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    flow = _owned(db, tenant_id, flow_id)
    version = db.get(FlowVersion, flow.active_version_id) if flow.active_version_id else _version(db, flow)
    if not version: raise HTTPException(404, "Flow version not found")
    return coverage_for_flow(db, tenant_id, flow, version)


@router.post("/{flow_id}/reconcile")
def reconcile(flow_id: str, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    from app.models.leads.lead import Lead
    flow = _owned(db, tenant_id, flow_id)
    if flow.status != "active" or not flow.active_version_id:
        raise HTTPException(409, "Activate the flow first.")
    version = db.get(FlowVersion, flow.active_version_id)
    ids = [row[0] for row in db.query(Lead.id).filter(Lead.tenant_id == tenant_id).all()]
    return enroll_leads(db, tenant_id, ids, "manual_reconciliation", pair=(flow, version))


@router.get("/{flow_id}/enrollments")
def enrollments(flow_id: str, db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    flow = _owned(db, tenant_id, flow_id)
    rows = db.query(FlowEnrollment).filter_by(flow_id=flow.id, tenant_id=tenant_id).order_by(FlowEnrollment.created_at.desc()).limit(250).all()
    return [{"id": str(r.id), "public_id": r.public_id, "lead_id": str(r.lead_id), "status": r.status, "current_node_key": r.current_node_key, "current_node_id": r.current_node_id, "enrollment_source": r.enrollment_source, "next_run_at": r.next_run_at.isoformat() if r.next_run_at else None, "stop_reason": r.stop_reason, "created_at": r.created_at.isoformat()} for r in rows]


@assets_router.get("")
def list_assets(db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    from app.models.flows import CommunicationAsset
    rows = db.query(CommunicationAsset).filter_by(tenant_id=tenant_id, status="ready").order_by(CommunicationAsset.created_at.desc()).all()
    return [{"id": str(a.id), "filename": a.filename, "content_type": a.content_type, "size_bytes": a.size_bytes, "category": a.category, "created_at": a.created_at.isoformat()} for a in rows]


@assets_router.post("", status_code=201)
async def upload_asset(file: UploadFile = File(...), db: Session = Depends(get_db), tenant_id: str = Depends(get_authenticated_tenant_id)):
    import hashlib, tempfile
    from pathlib import Path
    from uuid import uuid4
    from app.models.flows import CommunicationAsset
    from app.services.knowledge.object_storage import enabled, store_source
    if not enabled(): raise HTTPException(503, "Object storage is required for reusable communication assets.")
    data = await file.read()
    if not data or len(data) > 20 * 1024 * 1024: raise HTTPException(413, "Asset must be between 1 byte and 20 MB.")
    content_type = file.content_type or "application/octet-stream"
    allowed = content_type.startswith("image/") or content_type in {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "text/plain"}
    if not allowed: raise HTTPException(415, "Unsupported asset type.")
    asset_id = uuid4()
    with tempfile.TemporaryDirectory(prefix="follei-asset-") as directory:
        path = Path(directory) / (file.filename or "asset")
        path.write_bytes(data)
        object_key = store_source(path, tenant_id=str(tenant_id), job_id=f"communication-assets/{asset_id}")
    asset = CommunicationAsset(id=asset_id, tenant_id=tenant_id, filename=file.filename or "asset", object_key=object_key, content_type=content_type, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), category="image" if content_type.startswith("image/") else "document", status="ready")
    db.add(asset); db.commit()
    return {"id": str(asset.id), "filename": asset.filename, "content_type": asset.content_type, "size_bytes": asset.size_bytes, "category": asset.category}
