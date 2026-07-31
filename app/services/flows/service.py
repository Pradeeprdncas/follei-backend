from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.flows import FlowDefinition, FlowEnrollment, FlowExecutionStep, FlowVersion
from app.models.leads.lead import Lead
from app.models.campaigns import OutboxMessage
from app.core.public_id import generate_public_id


def ensure_graph_node_ids(graph: dict) -> dict:
    """Give every saved node an immutable, human-readable ID."""
    document = {**(graph or {})}
    nodes = []
    for raw in document.get("nodes") or []:
        node = {**raw}
        node.setdefault("id", generate_public_id("Node"))
        nodes.append(node)
    document["nodes"] = nodes
    document["edges"] = list(document.get("edges") or [])
    return document


def _next_business_time(db: Session, tenant_id: UUID, now: datetime) -> datetime:
    """Return UTC-naive now, or the tenant's next weekday 09:00."""
    from zoneinfo import ZoneInfo
    from app.models.tenancy import Tenant
    tenant = db.get(Tenant, tenant_id)
    try:
        zone = ZoneInfo((tenant.timezone if tenant else None) or "UTC")
    except Exception:
        zone = ZoneInfo("UTC")
    local = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone)
    if local.weekday() < 5 and 9 <= local.hour < 18:
        return now
    if local.hour >= 18:
        local += timedelta(days=1)
    while local.weekday() >= 5:
        local += timedelta(days=1)
    local = local.replace(hour=9, minute=0, second=0, microsecond=0)
    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def default_graph() -> dict:
    nodes = [
        {"key": "new_lead", "type": "trigger", "label": "New Lead", "position": {"x": 560, "y": 30}, "config": {}},
        {"key": "first_touch", "type": "wait", "label": "First touch", "position": {"x": 560, "y": 145}, "config": {"hours": 1}},
        {"key": "score", "type": "score_branch", "label": "AI Insights", "position": {"x": 560, "y": 260}, "config": {"hot_min": 80, "warm_min": 50}},
        {"key": "hot_email", "type": "send_email", "label": "Hot lead email", "position": {"x": 170, "y": 410}, "config": {"subject": "Let’s talk, {{CustomerName}}", "body": "Hi {{CustomerName}}, I noticed your interest in {{CompanyName}}. Would a quick conversation today help?", "asset_ids": []}},
        {"key": "warm_email", "type": "send_email", "label": "Warm lead email", "position": {"x": 560, "y": 410}, "config": {"subject": "A useful next step for {{CompanyName}}", "body": "Hi {{CustomerName}}, thanks for checking us out. Which part of the automation flow interested you most?", "asset_ids": []}},
        {"key": "cold_email", "type": "send_email", "label": "Cold lead drip", "position": {"x": 950, "y": 410}, "config": {"subject": "Automation ideas for {{CompanyName}}", "body": "Hi {{CustomerName}}, sharing a short update on practical sales automation. Happy to send details when useful.", "asset_ids": []}},
        {"key": "follow_up", "type": "wait", "label": "Follow-up interval", "position": {"x": 560, "y": 550}, "config": {"hours": 24}},
        {"key": "finish", "type": "stop", "label": "Nurture complete", "position": {"x": 560, "y": 680}, "config": {}},
    ]
    edges = [
        {"source": "new_lead", "target": "first_touch"},
        {"source": "first_touch", "target": "score"},
        {"source": "score", "target": "hot_email", "condition": "hot"},
        {"source": "score", "target": "warm_email", "condition": "warm"},
        {"source": "score", "target": "cold_email", "condition": "cold"},
        {"source": "hot_email", "target": "finish"},
        {"source": "warm_email", "target": "follow_up"},
        {"source": "cold_email", "target": "follow_up"},
        {"source": "follow_up", "target": "finish"},
    ]
    return ensure_graph_node_ids({"nodes": nodes, "edges": edges})


DEFAULT_SETTINGS = {
    "first_touch_hours": 1,
    "follow_up_hours": 24,
    "max_retries": 5,
    "business_hours_only": True,
    "stop_on_reply": True,
    "channels": ["email"],
    "auto_enroll_new_leads": True,
    "auto_enroll_existing": False,
    "start_immediately": True,
}


def ensure_default_flow(db: Session, tenant_id: str | UUID) -> FlowDefinition:
    flow = db.query(FlowDefinition).filter_by(tenant_id=tenant_id, category="pre_sales", is_default=True).first()
    if flow:
        return flow
    flow = FlowDefinition(tenant_id=tenant_id, name="Smart Customer Activity Tracking", category="pre_sales", status="draft", is_default=True)
    db.add(flow); db.flush()
    db.add(FlowVersion(tenant_id=tenant_id, flow_id=flow.id, version=1, status="draft", graph=default_graph(), settings=DEFAULT_SETTINGS))
    db.commit(); db.refresh(flow)
    return flow


def validate_graph(graph: dict, settings: dict) -> list[str]:
    errors: list[str] = []
    nodes = graph.get("nodes") or []
    keys = [node.get("key") for node in nodes]
    node_ids = [node.get("id") for node in nodes]
    if not nodes: errors.append("Flow needs at least one node.")
    if len(keys) != len(set(keys)): errors.append("Node keys must be unique.")
    if any(not value for value in node_ids): errors.append("Every node needs an immutable node ID.")
    if len(node_ids) != len(set(node_ids)): errors.append("Node IDs must be unique.")
    if not any(n.get("type") == "trigger" for n in nodes): errors.append("Flow needs a trigger node.")
    supported = {"trigger", "wait", "score_branch", "send_email", "stop", "create_task"}
    for node in nodes:
        if node.get("type") not in supported: errors.append(f"Unsupported node type: {node.get('type')}")
        if node.get("type") == "send_email" and not (node.get("config") or {}).get("body"): errors.append(f"{node.get('label') or node.get('key')} needs an email body.")
    for edge in graph.get("edges") or []:
        if edge.get("source") not in keys or edge.get("target") not in keys: errors.append("Every edge must reference existing nodes.")
    if int(settings.get("max_retries", 0)) < 0: errors.append("Max retries cannot be negative.")
    return errors


def active_flow(db: Session, tenant_id: str | UUID) -> tuple[FlowDefinition, FlowVersion] | None:
    flow = db.query(FlowDefinition).filter_by(tenant_id=tenant_id, category="pre_sales", is_default=True, status="active").first()
    if not flow or not flow.active_version_id: return None
    version = db.get(FlowVersion, flow.active_version_id)
    return (flow, version) if version else None


def lead_eligibility(lead: Lead) -> tuple[bool, str, dict]:
    profile = dict(lead.profile_data or {})
    email = str(lead.email or "").strip().lower()
    snapshot = {
        "email": email,
        "lead_status": lead.status,
        "suppressed": bool(profile.get("suppressed")),
        "marketing_consent": profile.get("marketing_consent"),
    }
    if not email or "@" not in email:
        return False, "missing_valid_email", snapshot
    if str(lead.status or "").lower() in {"disqualified", "converted", "lost", "customer"}:
        return False, f"lead_status:{lead.status}", snapshot
    if profile.get("suppressed") is True:
        return False, "suppressed", snapshot
    if profile.get("marketing_consent") is False:
        return False, "marketing_consent_denied", snapshot
    return True, "eligible", snapshot


def enroll_leads(
    db: Session,
    tenant_id: str | UUID,
    lead_ids: list[str | UUID],
    source: str = "lead_import",
    *,
    pair: tuple[FlowDefinition, FlowVersion] | None = None,
) -> dict:
    pair = pair or active_flow(db, tenant_id)
    if not pair:
        return {"status": "not_enrolled", "enrolled": 0, "reason": "flow_not_active"}
    flow, version = pair
    settings = {**DEFAULT_SETTINGS, **dict(version.settings or {})}
    automatic_sources = {"lead_import", "lead_import_job", "automatic_reconciliation"}
    if source in automatic_sources and not settings["auto_enroll_new_leads"]:
        return {
            "status": "not_enrolled",
            "enrolled": 0,
            "reason": "automatic_enrollment_disabled",
            "flow_id": str(flow.id),
            "flow_public_id": flow.public_id,
        }
    trigger = next(n for n in version.graph.get("nodes", []) if n.get("type") == "trigger")
    initial_delay_hours = 0.0 if settings["start_immediately"] else float(settings["first_touch_hours"])
    starts_at = datetime.utcnow() + timedelta(hours=initial_delay_hours)
    enrolled = 0
    already_enrolled = 0
    ineligible: list[dict] = []
    for lead_id in lead_ids:
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == tenant_id).first()
        if not lead:
            ineligible.append({"lead_id": str(lead_id), "reason": "lead_not_found"})
            continue
        eligible, reason, snapshot = lead_eligibility(lead)
        if not eligible:
            ineligible.append({"lead_id": str(lead.id), "reason": reason})
            continue
        exists = db.query(FlowEnrollment).filter(
            FlowEnrollment.lead_id == lead.id,
            FlowEnrollment.flow_id == flow.id,
            FlowEnrollment.status.in_(("running", "waiting")),
        ).first()
        if exists:
            already_enrolled += 1
            continue
        db.add(FlowEnrollment(
            tenant_id=tenant_id,
            flow_id=flow.id,
            flow_version_id=version.id,
            lead_id=lead.id,
            current_node_key=trigger["key"],
            current_node_id=trigger.get("id"),
            status="waiting" if initial_delay_hours else "running",
            next_run_at=starts_at,
            context={
                "source": source,
                "node_runs": {},
                "initial_trigger_delay_hours": initial_delay_hours,
            },
            enrollment_source=source,
            eligibility_snapshot=snapshot,
        ))
        enrolled += 1
    db.commit()
    return {
        "status": "enrolled" if enrolled else "no_change",
        "enrolled": enrolled,
        "already_enrolled": already_enrolled,
        "ineligible": ineligible,
        "flow_id": str(flow.id),
        "flow_public_id": flow.public_id,
        "flow_version_id": str(version.id),
        "version": version.version,
    }


def coverage_for_flow(db: Session, tenant_id: str | UUID, flow: FlowDefinition, version: FlowVersion) -> dict:
    leads = db.query(Lead).filter(Lead.tenant_id == tenant_id).order_by(Lead.created_at.desc()).all()
    enrollments = db.query(FlowEnrollment).filter(
        FlowEnrollment.tenant_id == tenant_id,
        FlowEnrollment.flow_id == flow.id,
    ).order_by(FlowEnrollment.created_at.desc()).all()
    by_lead: dict[str, FlowEnrollment] = {}
    for enrollment in enrollments:
        key = str(enrollment.lead_id)
        existing = by_lead.get(key)
        if existing is None or (
            enrollment.flow_version_id == version.id
            and existing.flow_version_id != version.id
        ):
            by_lead[key] = enrollment
    items = []
    eligible_count = enrolled_count = enrolled_eligible_count = active_count = 0
    for lead in leads:
        if (lead.profile_data or {}).get("merged_into"):
            continue
        eligible, reason, _ = lead_eligibility(lead)
        enrollment = by_lead.get(str(lead.id))
        if eligible:
            eligible_count += 1
        if enrollment:
            enrolled_count += 1
            if eligible:
                enrolled_eligible_count += 1
            if enrollment.status in ("running", "waiting"):
                active_count += 1
        items.append({
            "lead_id": str(lead.id),
            "lead_public_id": lead.public_id,
            "name": " ".join(filter(None, [lead.first_name, lead.last_name])) or lead.email,
            "email": lead.email,
            "company": lead.company,
            "eligible": eligible,
            "eligibility_reason": reason,
            "enrolled": enrollment is not None,
            "enrollment_id": str(enrollment.id) if enrollment else None,
            "enrollment_public_id": enrollment.public_id if enrollment else None,
            "flow_version_id": str(enrollment.flow_version_id) if enrollment else None,
            "on_active_version": bool(enrollment and enrollment.flow_version_id == version.id),
            "status": enrollment.status if enrollment else "not_enrolled",
            "current_node_key": enrollment.current_node_key if enrollment else None,
            "current_node_id": enrollment.current_node_id if enrollment else None,
            "next_run_at": enrollment.next_run_at.isoformat() if enrollment and enrollment.next_run_at else None,
            "stop_reason": enrollment.stop_reason if enrollment else None,
        })
    return {
        "flow_id": str(flow.id),
        "flow_public_id": flow.public_id,
        "flow_version_id": str(version.id),
        "version": version.version,
        "total_leads": len(items),
        "eligible_leads": eligible_count,
        "enrolled_leads": enrolled_count,
        "enrolled_eligible_leads": enrolled_eligible_count,
        "active_enrollments": active_count,
        "unenrolled_eligible": sum(item["eligible"] and not item["enrolled"] for item in items),
        "coverage_percent": round((enrolled_eligible_count / eligible_count) * 100, 1) if eligible_count else 100.0,
        "items": items,
    }


def reconcile_active_flows(db: Session) -> dict:
    """Continuously enroll missing leads according to each active version's trigger policy."""
    flows = db.query(FlowDefinition).filter(FlowDefinition.status == "active", FlowDefinition.active_version_id.isnot(None)).all()
    total = 0
    checked = 0
    for flow in flows:
        version = db.get(FlowVersion, flow.active_version_id)
        if not version:
            continue
        settings = dict(version.settings or {})
        if not settings.get("auto_enroll_new_leads", True) and not settings.get("auto_enroll_existing", False):
            continue
        query = db.query(Lead.id).filter(Lead.tenant_id == flow.tenant_id)
        if not settings.get("auto_enroll_existing", False) and version.published_at:
            query = query.filter(Lead.created_at >= version.published_at)
        ids = [row[0] for row in query.all()]
        checked += len(ids)
        result = enroll_leads(db, flow.tenant_id, ids, "automatic_reconciliation", pair=(flow, version))
        total += int(result.get("enrolled", 0))
    return {"flows_checked": len(flows), "leads_checked": checked, "enrolled": total}


def stop_for_reply(db: Session, tenant_id: str | UUID, lead_id: str | UUID, channel: str = "email") -> int:
    rows = db.query(FlowEnrollment).filter(FlowEnrollment.tenant_id == tenant_id, FlowEnrollment.lead_id == lead_id, FlowEnrollment.status.in_(("running", "waiting"))).all()
    stopped = 0
    for row in rows:
        version = db.get(FlowVersion, row.flow_version_id)
        if (version.settings or {}).get("stop_on_reply", True):
            row.status, row.stop_reason, row.completed_at = "stopped", f"reply_received:{channel}", datetime.utcnow()
            stopped += 1
    db.commit()
    return stopped


def _render(value: str, lead: Lead) -> str:
    name = " ".join(filter(None, [lead.first_name, lead.last_name])) or "there"
    return (value or "").replace("{{CustomerName}}", name).replace("{{CompanyName}}", lead.company or "your company").replace("{{name}}", name)


def process_due(db: Session, limit: int = 25) -> int:
    now = datetime.utcnow()
    rows = db.query(FlowEnrollment).filter(FlowEnrollment.status.in_(("running", "waiting")), (FlowEnrollment.next_run_at.is_(None)) | (FlowEnrollment.next_run_at <= now)).order_by(FlowEnrollment.next_run_at.asc()).limit(limit).all()
    processed = 0
    for enrollment in rows:
        version, lead = db.get(FlowVersion, enrollment.flow_version_id), db.get(Lead, enrollment.lead_id)
        if not version or not lead:
            enrollment.status, enrollment.stop_reason = "stopped", "missing_flow_or_lead"; continue
        graph, context = version.graph or {}, dict(enrollment.context or {})
        node = next((n for n in graph.get("nodes", []) if n.get("key") == enrollment.current_node_key), None)
        if not node:
            enrollment.status, enrollment.stop_reason = "stopped", "missing_node"; continue
        runs = dict(context.get("node_runs") or {}); attempt = int(runs.get(node["key"], 0)) + 1
        idempotency = f"{enrollment.id}:{node['key']}:{attempt}"
        if db.query(FlowExecutionStep).filter_by(idempotency_key=idempotency).first(): continue
        output: dict = {}
        next_key = None
        edges = [e for e in graph.get("edges", []) if e.get("source") == node["key"]]
        kind = node.get("type")
        if kind == "send_email" and (version.settings or {}).get("business_hours_only", True):
            business_time = _next_business_time(db, enrollment.tenant_id, now)
            if business_time > now:
                enrollment.status, enrollment.next_run_at = "waiting", business_time
                continue
        if kind == "wait":
            hours = float((node.get("config") or {}).get("hours", 0))
            if enrollment.status != "waiting":
                enrollment.status, enrollment.next_run_at = "waiting", now + timedelta(hours=hours)
                continue
            enrollment.status, enrollment.next_run_at = "running", now
        if kind == "score_branch":
            score = float(lead.current_score or lead.revenue_score or 0)
            cfg = node.get("config") or {}
            branch = "hot" if score >= cfg.get("hot_min", 80) else "warm" if score >= cfg.get("warm_min", 50) else "cold"
            output = {"score": score, "branch": branch}
            next_key = next((e["target"] for e in edges if e.get("condition") == branch), None)
        elif kind == "send_email":
            cfg = node.get("config") or {}
            outbox = OutboxMessage(tenant_id=enrollment.tenant_id, channel="email", recipient=lead.email, subject=_render(cfg.get("subject", ""), lead), body=_render(cfg.get("body", ""), lead), html_body=_render(cfg.get("body", ""), lead), metadata_={"tenant_id": str(enrollment.tenant_id), "lead_id": str(lead.id), "flow_enrollment_id": str(enrollment.id), "asset_ids": cfg.get("asset_ids", [])}, status="pending", priority=5, max_retries=int((version.settings or {}).get("max_retries", 5)))
            db.add(outbox); db.flush(); output = {"outbox_id": str(outbox.id)}
        elif kind == "stop":
            enrollment.status, enrollment.completed_at, enrollment.stop_reason = "completed", now, "flow_complete"
        if next_key is None and edges: next_key = edges[0]["target"]
        runs[node["key"]] = attempt; context["node_runs"] = runs; enrollment.context = context
        db.add(FlowExecutionStep(tenant_id=enrollment.tenant_id, enrollment_id=enrollment.id, lead_id=lead.id, node_key=node["key"], node_id=node.get("id"), action_type=kind, attempt=attempt, idempotency_key=idempotency, status="completed", output=output, completed_at=now))
        try:
            from app.services.knowledge.memory_store import append_lead_flow_event
            append_lead_flow_event(tenant_id=str(enrollment.tenant_id), lead_id=str(lead.id), enrollment_id=str(enrollment.id), node_key=node["key"], event_type=kind, data={"attempt": attempt, **output})
        except Exception:
            pass
        if enrollment.status not in ("completed", "stopped"):
            if next_key:
                enrollment.current_node_key = next_key
                next_node = next((item for item in graph.get("nodes", []) if item.get("key") == next_key), None)
                enrollment.current_node_id = next_node.get("id") if next_node else None
            else: enrollment.status, enrollment.completed_at, enrollment.stop_reason = "completed", now, "no_next_node"
        processed += 1
    db.commit()
    return processed
