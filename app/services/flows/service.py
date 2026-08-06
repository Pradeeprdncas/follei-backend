from __future__ import annotations

from datetime import datetime, timedelta
from copy import deepcopy
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from app.models.flows import (
    FlowDefinition, FlowEnrollment, FlowExecutionStep, FlowVersion,
    TenantWorkflowInstance, WorkflowApproval, WorkflowTemplate,
)
from app.models.leads.lead import Lead
from app.models.customers.customer import Customer
from app.models.agents.agent import AgentTask
from app.models.tenancy import User
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

NODE_CONTRACT_KEYS = {"purpose", "inputs", "execution", "decision", "output", "verification", "escalation", "audit"}


def _contract(**values: object) -> dict:
    """Keep every template node auditable even before a policy compiler exists."""
    return {key: values.get(key, "") for key in NODE_CONTRACT_KEYS}


def _template_graph(slug: str, nodes: list[dict], edges: list[dict]) -> dict:
    stable_nodes = []
    for raw in deepcopy(nodes):
        raw["id"] = "NODE_" + uuid5(NAMESPACE_URL, f"follei:{slug}:{raw['key']}").hex[:16].upper()
        stable_nodes.append(raw)
    return {"nodes": stable_nodes, "edges": deepcopy(edges)}


def universal_template_spec() -> dict:
    slots = [
        ("intake_identification", "Intake & Identification"),
        ("segmentation_routing", "Segmentation & Routing"),
        ("engagement", "Engagement"),
        ("preparation_documentation", "Preparation & Documentation"),
        ("handoff_approval", "Handoff & Approval"),
        ("fulfillment", "Fulfillment"),
        ("ongoing_relationship", "Ongoing Relationship"),
    ]
    nodes = [{"key": "start", "type": "trigger", "label": "New Business Event", "position": {"x": 20, "y": 140}, "config": {}}] + [{"key": key, "type": "subflow", "label": label, "position": {"x": 100 + index * 180, "y": 140}, "config": {"child_template_slug": f"generic-{key}", "optional": True}} for index, (key, label) in enumerate(slots)]
    return {
        "slug": "universal-tenant-flow", "industry": "universal", "name": "Universal Tenant Flow", "version": 1,
        "graph": _template_graph("universal-tenant-flow", nodes, [{"source": "start", "target": slots[0][0]}] + [{"source": slots[i][0], "target": slots[i + 1][0]} for i in range(len(slots) - 1)]),
        "node_contracts": {"start": _contract(purpose="Start a tenant business case.", inputs="Inbound event.", execution="Code enrollment.", decision="Begin workflow.", output="Case context.", verification="Enrollment created.", escalation="None.", audit="Enrollment source and timestamp."), **{key: _contract(
            purpose=f"Universal business lifecycle slot: {label}.", inputs="Tenant context and case state.",
            execution="Runs the attached tenant or industry child workflow.", decision="Child workflow completion outcome.",
            output="Child workflow's structured output.", verification="Child completion and execution evidence are persisted.",
            escalation="Child workflow may require an approval gate.", audit="Template version, child workflow and node executions."
        ) for key, label in slots}},
        "settings": {"business_hours_only": True},
    }


def insurance_template_spec() -> dict:
    """Compatibility view of the pack's complete lead-to-application journey."""
    nodes = [
        {"key": "start", "type": "trigger", "label": "Insurance Lead Arrives", "position": {"x": 0, "y": 160}, "config": {}},
        {"key": "intake_prescreen", "type": "intake_prescreen", "label": "Lead Intake & Pre-screen", "position": {"x": 80, "y": 160}, "config": {"allowed_outcomes": ["ready_for_contact", "needs_more_information", "not_contactable", "consent_missing", "out_of_scope", "human_review_required"]}},
        {"key": "first_contact", "type": "event_branch", "label": "First Contact Attempt", "position": {"x": 300, "y": 160}, "config": {"allowed_events": ["connected_interested", "connected_busy", "no_answer", "not_interested", "requests_human"]}},
        {"key": "plan_nurture", "type": "send_email", "label": "Needs Discovery & Plan Nurture", "position": {"x": 520, "y": 160}, "config": {"subject": "Your insurance options", "body": "Hi {{CustomerName}}, we can help you understand the next approved options for your needs.", "asset_ids": []}},
        {"key": "quote_preparation", "type": "document_check", "label": "Quote / Application Preparation", "position": {"x": 740, "y": 160}, "config": {"required_fields": ["product_interest", "contact_consent"]}},
        {"key": "human_handoff", "type": "approval_gate", "label": "Human Sales / Underwriting Handoff", "position": {"x": 960, "y": 160}, "config": {"action": "insurance_handoff", "hard_gate": True}},
        {"key": "complete", "type": "stop", "label": "Auditable Completion", "position": {"x": 1180, "y": 160}, "config": {}},
    ]
    contracts = {
        "start": _contract(purpose="Begin an insurance lead case.", inputs="Inbound lead event.", execution="Code enrollment.", decision="Begin pre-screen.", output="Case context.", verification="Enrollment created.", escalation="None.", audit="Source and timestamp."),
        "intake_prescreen": _contract(purpose="Determine legitimate contactability without promising eligibility.", inputs="Raw lead, consent and product context.", execution="Deterministic dedupe, normalization and consent checks.", decision="Allowed pre-screen outcome.", output="Status and missing fields.", verification="Canonical lead record and dedupe result.", escalation="Ambiguous duplicate or out-of-scope request.", audit="Source, consent and dedupe reasoning."),
        "first_contact": _contract(purpose="Establish reachability and interest only.", inputs="Lead, consent and interaction history.", execution="Channel action plus code-validated event capture.", decision="Allowed contact event.", output="Structured contact outcome.", verification="Provider receipt/transcript when available.", escalation="Human request.", audit="Provider receipt, transcript and extracted evidence."),
        "plan_nurture": _contract(purpose="Guide product-specific discovery using approved knowledge.", inputs="Prior outcome and approved tenant knowledge.", execution="AI proposes content; code sends only approved content.", decision="Ready, continue discovery, or licensed-agent route.", output="Needs profile and objections.", verification="Citations and conversation are persisted.", escalation="Advice, negotiation or exception.", audit="Sources, model version and conversation."),
        "quote_preparation": _contract(purpose="Prepare a complete application package, never finalize it.", inputs="Needs profile and document checklist.", execution="Deterministic field/document validation; AI may draft approved text.", decision="Ready, missing information or out-of-policy.", output="Checklist and structured application fields.", verification="Required data validated before handoff.", escalation="Out-of-policy or final decision.", audit="Validation result and draft version."),
        "human_handoff": _contract(purpose="Create a human-owned consequential decision queue.", inputs="Prepared case and escalation rules.", execution="Code-only approval/queue record.", decision="Pending, approved or rejected.", output="Assignment/approval status.", verification="Canonical approval record and SLA-able timestamp.", escalation="This node is the escalation path.", audit="Full prior node history and approver."),
        "complete": _contract(purpose="Close this automation path after verified handoff.", inputs="Prior node output.", execution="Code-only completion.", decision="Complete.", output="Completion timestamp.", verification="All execution records exist.", escalation="None.", audit="Versioned execution trace."),
    }
    return {"slug": "insurance-lead-to-application", "industry": "insurance", "name": "Insurance / Lead-to-Application", "version": 1, "graph": _template_graph("insurance-lead-to-application", nodes, [{"source": nodes[i]["key"], "target": nodes[i + 1]["key"]} for i in range(len(nodes) - 1)]), "node_contracts": contracts, "settings": {**DEFAULT_SETTINGS, "channels": ["email"], "requires_human_approval": True}}


def _child_template(slug: str, name: str, nodes: list[dict], edges: list[dict], contracts: dict) -> dict:
    start = {"key": "start", "type": "trigger", "label": "Start", "position": {"x": 0, "y": 120}, "config": {}}
    finish = {"key": "complete", "type": "stop", "label": "Complete", "position": {"x": 900, "y": 120}, "config": {}}
    base_contracts = {
        "start": _contract(purpose="Start this child workflow.", inputs="Parent case context.", execution="Code enrollment.", decision="Begin.", output="Child context.", verification="Child enrollment exists.", escalation="None.", audit="Parent enrollment and template version."),
        "complete": _contract(purpose="Return verified output to the parent node.", inputs="Child node outputs.", execution="Code completion.", decision="Complete.", output="Structured child result.", verification="Execution trace persisted.", escalation="None.", audit="All child steps and timestamps."),
    }
    return {"slug": slug, "industry": "insurance", "name": name, "version": 1, "graph": _template_graph(slug, [start, *nodes, finish], [{"source": "start", "target": nodes[0]["key"]}, *edges]), "node_contracts": {**base_contracts, **contracts}, "settings": {**DEFAULT_SETTINGS, "channels": ["email"], "auto_enroll_new_leads": False, "auto_enroll_existing": False, "requires_human_approval": "handoff" in slug}}


def insurance_child_template_specs() -> list[dict]:
    intake_node = {"key": "intake_prescreen", "type": "intake_prescreen", "label": "Lead Intake & Pre-screen", "position": {"x": 260, "y": 120}, "config": {"allowed_outcomes": ["ready_for_contact", "needs_more_information", "not_contactable", "consent_missing", "out_of_scope", "human_review_required"]}}
    routing_node = {"key": "customer_route", "type": "customer_route", "label": "New Lead Route", "position": {"x": 260, "y": 120}, "config": {"allowed_outcomes": ["new_lead", "existing_customer"]}}
    engagement_nodes = [
        {"key": "first_contact", "type": "event_branch", "label": "First Contact Outcome", "position": {"x": 180, "y": 120}, "config": {"allowed_events": ["connected_interested", "connected_busy", "no_answer", "not_interested", "requests_human"], "required_payload": ["channel"], "required_payload_by_event": {"connected_interested": ["contact_receipt_id", "consent_to_continue", "product_interest", "urgency", "objections", "qualification_evidence"], "connected_busy": ["preferred_callback_at"], "no_answer": ["contact_receipt_id"]}}},
        {"key": "plan_nurture", "type": "send_email", "label": "Approved Plan Nurture", "position": {"x": 430, "y": 120}, "config": {"subject": "Your insurance options", "body": "Hi {{CustomerName}}, we can help you understand the next approved options for your needs.", "asset_ids": []}},
        {"key": "discovery_outcome", "type": "event_branch", "label": "Structured Discovery Outcome", "position": {"x": 660, "y": 120}, "config": {"allowed_events": ["ready_for_quote", "needs_more_discovery", "licensed_agent_required"], "required_payload": ["needs_profile", "citations", "model_version", "conversation_id"]}},
        {"key": "callback_task", "type": "create_task", "label": "Schedule Callback", "position": {"x": 430, "y": 300}, "config": {"task_type": "insurance_callback"}},
        {"key": "followup_email", "type": "send_email", "label": "No-answer Follow-up", "position": {"x": 660, "y": 300}, "config": {"subject": "A convenient time to connect", "body": "Hi {{CustomerName}}, we tried to reach you about your insurance enquiry. Reply with a convenient time.", "asset_ids": []}},
        {"key": "human_request", "type": "approval_gate", "label": "Immediate Human Request", "position": {"x": 660, "y": 420}, "config": {"action": "licensed_agent_request", "hard_gate": True, "sla_hours": 1}},
    ]
    document_node = {"key": "quote_preparation", "type": "document_check", "label": "Quote / Application Preparation", "position": {"x": 260, "y": 120}, "config": {"required_fields": ["product_interest", "contact_consent"]}}
    handoff_node = {"key": "human_handoff", "type": "approval_gate", "label": "Human Sales / Underwriting Handoff", "position": {"x": 260, "y": 120}, "config": {"action": "insurance_handoff", "hard_gate": True, "sla_hours": 4}}
    return [
        _child_template("insurance-intake-prescreen", "Insurance / Intake & Pre-screen", [intake_node], [{"source": "intake_prescreen", "target": "complete"}], {"intake_prescreen": insurance_template_spec()["node_contracts"]["intake_prescreen"]}),
        _child_template("insurance-new-lead-routing", "Insurance / New Lead Routing", [routing_node], [{"source": "customer_route", "target": "complete", "condition": "new_lead"}], {"customer_route": _contract(purpose="Route this vertical slice only to new leads.", inputs="Canonical lead and customer records.", execution="Deterministic customer lookup.", decision="New lead or existing customer.", output="Route outcome.", verification="Lookup is tenant-scoped.", escalation="Existing-customer journeys are out of this slice.", audit="Lookup result and identifiers.")}),
        _child_template("insurance-engagement", "Insurance / Engagement", engagement_nodes, [
            {"source": "first_contact", "target": "plan_nurture", "condition": "connected_interested"},
            {"source": "first_contact", "target": "callback_task", "condition": "connected_busy"},
            {"source": "first_contact", "target": "followup_email", "condition": "no_answer"},
            {"source": "first_contact", "target": "complete", "condition": "not_interested"},
            {"source": "first_contact", "target": "human_request", "condition": "requests_human"},
            {"source": "plan_nurture", "target": "discovery_outcome"},
            {"source": "discovery_outcome", "target": "complete", "condition": "ready_for_quote"},
            {"source": "discovery_outcome", "target": "plan_nurture", "condition": "needs_more_discovery"},
            {"source": "discovery_outcome", "target": "human_request", "condition": "licensed_agent_required"},
            {"source": "callback_task", "target": "complete"}, {"source": "followup_email", "target": "complete"}, {"source": "human_request", "target": "complete"},
        ], {"first_contact": insurance_template_spec()["node_contracts"]["first_contact"], "plan_nurture": insurance_template_spec()["node_contracts"]["plan_nurture"], "discovery_outcome": insurance_template_spec()["node_contracts"]["plan_nurture"], "callback_task": _contract(purpose="Schedule the requested callback.", inputs="Preferred callback time and channel.", execution="Code task creation.", decision="Task queued.", output="Task identifier.", verification="Task exists.", escalation="None.", audit="Due time and case context."), "followup_email": _contract(purpose="Follow up after no answer.", inputs="Lead and consent.", execution="Email outbox.", decision="Queued or failed.", output="Outbox identifier.", verification="Durable outbox record.", escalation="Provider failure retry policy.", audit="Message and provider status."), "human_request": insurance_template_spec()["node_contracts"]["human_handoff"]}),
        _child_template("insurance-quote-preparation", "Insurance / Quote Preparation", [document_node], [{"source": "quote_preparation", "target": "complete"}], {"quote_preparation": insurance_template_spec()["node_contracts"]["quote_preparation"]}),
        _child_template("insurance-human-handoff", "Insurance / Human Handoff", [handoff_node], [{"source": "human_handoff", "target": "complete"}], {"human_handoff": insurance_template_spec()["node_contracts"]["human_handoff"]}),
    ]


def ensure_workflow_templates(db: Session) -> dict[str, WorkflowTemplate]:
    templates: dict[str, WorkflowTemplate] = {}
    for spec in (universal_template_spec(), insurance_template_spec(), *insurance_child_template_specs()):
        errors = validate_graph(spec["graph"], spec["settings"]) + validate_node_contracts(spec["graph"], spec["node_contracts"])
        if errors:
            raise ValueError(f"Invalid built-in workflow template {spec['slug']}: {errors}")
        template = db.query(WorkflowTemplate).filter_by(industry=spec["industry"], slug=spec["slug"], version=spec["version"]).first()
        if not template:
            template = WorkflowTemplate(**spec, status="published", published_at=datetime.utcnow())
            db.add(template); db.flush()
        templates[spec["slug"]] = template
    return templates


def instantiate_template(db: Session, tenant_id: str | UUID, template: WorkflowTemplate, *, parent_instance: TenantWorkflowInstance | None = None, parent_node_key: str | None = None) -> TenantWorkflowInstance:
    existing = db.query(TenantWorkflowInstance).filter_by(tenant_id=tenant_id, template_id=template.id, parent_instance_id=parent_instance.id if parent_instance else None, parent_node_key=parent_node_key).first()
    if existing:
        return existing
    flow = FlowDefinition(tenant_id=tenant_id, name=template.name, category=f"template:{template.industry}:{template.slug}", status="draft", is_default=False)
    db.add(flow); db.flush()
    version = FlowVersion(tenant_id=tenant_id, flow_id=flow.id, version=1, status="draft", graph=ensure_graph_node_ids(template.graph), settings={**DEFAULT_SETTINGS, **dict(template.settings or {})})
    db.add(version); db.flush()
    instance = TenantWorkflowInstance(tenant_id=tenant_id, template_id=template.id, flow_id=flow.id, parent_instance_id=parent_instance.id if parent_instance else None, parent_node_key=parent_node_key, name=template.name, status="active", overrides={})
    db.add(instance); db.flush()
    return instance


def ensure_tenant_workflow_runtime(db: Session, tenant_id: str | UUID, industry: str | None = None) -> dict[str, TenantWorkflowInstance]:
    templates = ensure_workflow_templates(db)
    universal = instantiate_template(db, tenant_id, templates["universal-tenant-flow"])
    results = {"universal": universal}
    if str(industry or "").strip().lower() in {"insurance", "financial services"}:
        slot_templates = {
            "intake_identification": "insurance-intake-prescreen",
            "segmentation_routing": "insurance-new-lead-routing",
            "engagement": "insurance-engagement",
            "preparation_documentation": "insurance-quote-preparation",
            "handoff_approval": "insurance-human-handoff",
        }
        root_version = db.query(FlowVersion).filter_by(flow_id=universal.flow_id).order_by(FlowVersion.version.desc()).first()
        root_graph = ensure_graph_node_ids(root_version.graph)
        for slot, template_slug in slot_templates.items():
            child = instantiate_template(db, tenant_id, templates[template_slug], parent_instance=universal, parent_node_key=slot)
            results[slot] = child
            node = next(item for item in root_graph["nodes"] if item["key"] == slot)
            node.setdefault("config", {})["child_flow_id"] = str(child.flow_id)
            node["config"]["child_workflow_instance_id"] = str(child.id)
        for slot in ("fulfillment", "ongoing_relationship"):
            node = next(item for item in root_graph["nodes"] if item["key"] == slot)
            node.setdefault("config", {})["optional"] = True
        root_version.graph = root_graph
    db.commit()
    return results


def activate_tenant_workflow_runtime(db: Session, tenant_id: str | UUID, industry: str) -> dict[str, TenantWorkflowInstance]:
    instances = ensure_tenant_workflow_runtime(db, tenant_id, industry)
    for instance in instances.values():
        flow = db.get(FlowDefinition, instance.flow_id)
        version = db.query(FlowVersion).filter_by(flow_id=flow.id).order_by(FlowVersion.version.desc()).first()
        errors = validate_graph(version.graph or {}, version.settings or {})
        if errors:
            raise ValueError(f"Workflow {instance.name} is invalid: {errors}")
        version.status, version.published_at = "published", datetime.utcnow()
        flow.status, flow.active_version_id = "active", version.id
    db.commit()
    return instances


def apply_workflow_overrides(db: Session, tenant_id: str | UUID, instance: TenantWorkflowInstance, overrides: dict) -> FlowVersion:
    allowed_keys = {"disabled_node_keys", "node_config", "added_nodes", "added_edges", "settings"}
    unknown = sorted(set(overrides) - allowed_keys)
    if unknown:
        raise ValueError(f"Unsupported override fields: {', '.join(unknown)}")
    template = db.get(WorkflowTemplate, instance.template_id)
    graph = deepcopy(template.graph or {})
    disabled = set(overrides.get("disabled_node_keys") or [])
    protected = {node["key"] for node in graph.get("nodes", []) if node.get("type") in {"trigger", "approval_gate", "stop"}}
    forbidden = sorted(disabled & protected)
    if forbidden:
        raise ValueError(f"Protected workflow nodes cannot be disabled: {', '.join(forbidden)}")
    graph["nodes"] = [node for node in graph.get("nodes", []) if node.get("key") not in disabled]
    graph["edges"] = [edge for edge in graph.get("edges", []) if edge.get("source") not in disabled and edge.get("target") not in disabled]
    by_key = {node["key"]: node for node in graph["nodes"]}
    for key, config in dict(overrides.get("node_config") or {}).items():
        if key not in by_key:
            raise ValueError(f"Cannot configure unknown node {key!r}")
        if by_key[key].get("type") == "approval_gate" and config.get("hard_gate") is False:
            raise ValueError("A hard approval gate cannot be downgraded by a tenant override")
        by_key[key]["config"] = {**dict(by_key[key].get("config") or {}), **dict(config or {})}
    contracts = dict(template.node_contracts or {})
    for raw in list(overrides.get("added_nodes") or []):
        node = deepcopy(raw); contract = dict(node.pop("contract", {}) or {})
        if not node.get("key") or node["key"] in by_key:
            raise ValueError("Every added node needs a unique key")
        missing = sorted(key for key in NODE_CONTRACT_KEYS if not str(contract.get(key) or "").strip())
        if missing:
            raise ValueError(f"Added node {node['key']} is missing contract fields: {', '.join(missing)}")
        graph["nodes"].append(node); by_key[node["key"]] = node; contracts[node["key"]] = contract
    graph["edges"].extend(deepcopy(list(overrides.get("added_edges") or [])))
    graph = ensure_graph_node_ids(graph)
    settings = {**DEFAULT_SETTINGS, **dict(template.settings or {}), **dict(overrides.get("settings") or {})}
    errors = validate_graph(graph, settings) + validate_node_contracts(graph, contracts)
    if errors:
        raise ValueError(f"Invalid workflow override: {errors}")
    latest = db.query(FlowVersion).filter_by(flow_id=instance.flow_id).order_by(FlowVersion.version.desc()).first()
    version = FlowVersion(tenant_id=tenant_id, flow_id=instance.flow_id, version=(latest.version if latest else 0) + 1, status="draft", graph=graph, settings=settings)
    db.add(version); instance.overrides = deepcopy(overrides); db.commit(); db.refresh(version)
    try:
        from app.services.knowledge.memory_store import upsert_workflow_override_memory
        upsert_workflow_override_memory(tenant_id=str(tenant_id), workflow_instance_id=str(instance.id), flow_version_id=str(version.id), version=version.version, overrides=overrides)
    except Exception:
        pass
    return version


def activate_workflow_instance(db: Session, tenant_id: str | UUID, instance: TenantWorkflowInstance) -> FlowVersion:
    if str(instance.tenant_id) != str(tenant_id):
        raise ValueError("Workflow instance not found")
    flow = db.get(FlowDefinition, instance.flow_id)
    version = db.query(FlowVersion).filter_by(flow_id=flow.id).order_by(FlowVersion.version.desc()).first()
    errors = validate_graph(version.graph or {}, version.settings or {})
    if errors:
        raise ValueError(f"Workflow is invalid: {errors}")
    version.status, version.published_at = "published", datetime.utcnow()
    flow.status, flow.active_version_id = "active", version.id
    db.commit(); db.refresh(version)
    return version


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
    supported = {"trigger", "wait", "score_branch", "send_email", "stop", "create_task", "subflow", "intake_prescreen", "customer_route", "event_branch", "document_check", "approval_gate", "handoff"}
    for node in nodes:
        if node.get("type") not in supported: errors.append(f"Unsupported node type: {node.get('type')}")
        if node.get("type") == "send_email" and not (node.get("config") or {}).get("body"): errors.append(f"{node.get('label') or node.get('key')} needs an email body.")
        if node.get("type") == "event_branch" and not (node.get("config") or {}).get("allowed_events"):
            errors.append(f"{node.get('label') or node.get('key')} needs allowed events.")
        if node.get("type") == "approval_gate" and not (node.get("config") or {}).get("action"):
            errors.append(f"{node.get('label') or node.get('key')} needs an approval action.")
    for edge in graph.get("edges") or []:
        if edge.get("source") not in keys or edge.get("target") not in keys: errors.append("Every edge must reference existing nodes.")
    if int(settings.get("max_retries", 0)) < 0: errors.append("Max retries cannot be negative.")
    return errors


def validate_node_contracts(graph: dict, node_contracts: dict) -> list[str]:
    """Templates are rejected when a business node lacks any contract element."""
    errors: list[str] = []
    for node in graph.get("nodes") or []:
        contract = dict((node_contracts or {}).get(node.get("key")) or {})
        missing = sorted(key for key in NODE_CONTRACT_KEYS if not str(contract.get(key) or "").strip())
        if missing:
            errors.append(f"{node.get('key')} is missing node contract fields: {', '.join(missing)}")
    return errors


def active_flow(db: Session, tenant_id: str | UUID) -> tuple[FlowDefinition, FlowVersion] | None:
    instance = db.query(TenantWorkflowInstance).join(WorkflowTemplate, TenantWorkflowInstance.template_id == WorkflowTemplate.id).filter(
        TenantWorkflowInstance.tenant_id == tenant_id,
        TenantWorkflowInstance.status == "active",
        WorkflowTemplate.slug == "universal-tenant-flow",
    ).first()
    if instance:
        industry_flow = db.get(FlowDefinition, instance.flow_id)
        if industry_flow and industry_flow.status == "active" and industry_flow.active_version_id:
            industry_version = db.get(FlowVersion, industry_flow.active_version_id)
            if industry_version:
                return industry_flow, industry_version
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


def record_node_event(db: Session, tenant_id: str | UUID, enrollment_id: str | UUID, event: str, payload: dict | None = None) -> FlowEnrollment:
    """Accept only the event vocabulary declared by the waiting node."""
    enrollment = db.query(FlowEnrollment).filter_by(id=enrollment_id, tenant_id=tenant_id).first()
    if not enrollment or enrollment.status != "waiting_event":
        raise ValueError("No workflow enrollment is waiting for an event")
    version = db.get(FlowVersion, enrollment.flow_version_id)
    node = next((item for item in (version.graph or {}).get("nodes", []) if item.get("key") == enrollment.current_node_key), None)
    allowed = set((node or {}).get("config", {}).get("allowed_events") or [])
    if event not in allowed:
        raise ValueError(f"Event {event!r} is not allowed for this node")
    payload = dict(payload or {})
    forbidden_raw = sorted(key for key in {"transcript", "raw_transcript", "audio", "raw_payload"} if key in payload)
    if forbidden_raw:
        raise ValueError(f"Raw high-volume content must be stored in memory/object storage and referenced by ID: {', '.join(forbidden_raw)}")
    config = (node or {}).get("config", {})
    required = set(config.get("required_payload") or []) | set((config.get("required_payload_by_event") or {}).get(event, []))
    missing = sorted(key for key in required if payload.get(key) in (None, "", [], {}))
    if missing:
        raise ValueError(f"Event payload is missing required fields: {', '.join(missing)}")
    context = dict(enrollment.context or {}); events = dict(context.get("events") or {}); events[node["key"]] = {"outcome": event, "payload": payload, "recorded_at": datetime.utcnow().isoformat()}; context["events"] = events
    enrollment.context, enrollment.status, enrollment.next_run_at = context, "running", datetime.utcnow()
    db.commit(); db.refresh(enrollment)
    return enrollment


def record_documents(db: Session, tenant_id: str | UUID, enrollment_id: str | UUID, fields: dict) -> FlowEnrollment:
    """Merge reviewed application fields and resume only a document-check node."""
    enrollment = db.query(FlowEnrollment).filter_by(id=enrollment_id, tenant_id=tenant_id).first()
    if not enrollment or enrollment.status not in {"waiting_documents", "waiting_input"}:
        raise ValueError("No workflow enrollment is waiting for application input")
    lead = db.get(Lead, enrollment.lead_id)
    if not lead:
        raise ValueError("Lead not found")
    cleaned = {str(key): value for key, value in dict(fields or {}).items() if value not in (None, "", [], {})}
    if not cleaned:
        raise ValueError("At least one non-empty application field is required")
    lead.profile_data = {**dict(lead.profile_data or {}), **cleaned}
    context = dict(enrollment.context or {}); submissions = list(context.get("document_submissions") or []); submissions.append({"fields": sorted(cleaned), "recorded_at": datetime.utcnow().isoformat()}); context["document_submissions"] = submissions
    enrollment.context, enrollment.status, enrollment.next_run_at = context, "running", datetime.utcnow()
    db.commit(); db.refresh(enrollment)
    return enrollment


def decide_approval(db: Session, tenant_id: str | UUID, approval_id: str | UUID, approved: bool, decided_by: str | UUID, metadata: dict | None = None) -> WorkflowApproval:
    approval = db.query(WorkflowApproval).filter_by(id=approval_id, tenant_id=tenant_id).first()
    if not approval or approval.status != "pending":
        raise ValueError("Approval is not pending")
    approval.status = "approved" if approved else "rejected"
    approval.decided_by, approval.decided_at, approval.decision_metadata = decided_by, datetime.utcnow(), dict(metadata or {})
    task = db.get(AgentTask, approval.task_id) if approval.task_id else None
    if task:
        task.status = "completed" if approved else "cancelled"
        task.payload = {**dict(task.payload or {}), "approval_status": approval.status, "decision_metadata": approval.decision_metadata}
    enrollment = db.get(FlowEnrollment, approval.enrollment_id) if approval.enrollment_id else None
    if enrollment and enrollment.status == "waiting_approval":
        if approved:
            version = db.get(FlowVersion, enrollment.flow_version_id)
            edges = [edge for edge in (version.graph or {}).get("edges", []) if edge.get("source") == enrollment.current_node_key]
            next_key = edges[0].get("target") if edges else None
            if next_key:
                enrollment.current_node_key, enrollment.status, enrollment.next_run_at = next_key, "running", datetime.utcnow()
                next_node = next((item for item in (version.graph or {}).get("nodes", []) if item.get("key") == next_key), None)
                enrollment.current_node_id = next_node.get("id") if next_node else None
            else:
                enrollment.status, enrollment.completed_at, enrollment.stop_reason = "completed", datetime.utcnow(), "approval_complete"
        else:
            enrollment.status, enrollment.completed_at, enrollment.stop_reason = "stopped", datetime.utcnow(), "approval_rejected"
    db.commit(); db.refresh(approval)
    return approval


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
        workflow_instance = db.query(TenantWorkflowInstance).filter_by(flow_id=enrollment.flow_id, tenant_id=enrollment.tenant_id).first()
        workflow_template = db.get(WorkflowTemplate, workflow_instance.template_id) if workflow_instance else None
        graph, context = version.graph or {}, dict(enrollment.context or {})
        node = next((n for n in graph.get("nodes", []) if n.get("key") == enrollment.current_node_key), None)
        if not node:
            enrollment.status, enrollment.stop_reason = "stopped", "missing_node"; continue
        runs = dict(context.get("node_runs") or {}); attempt = int(runs.get(node["key"], 0)) + 1
        idempotency = f"{enrollment.id}:{node['key']}:{attempt}"
        if db.query(FlowExecutionStep).filter_by(idempotency_key=idempotency).first(): continue
        output: dict = {}
        decision: dict = {}
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
            decision = {"outcome": branch, "score": score}
            next_key = next((e["target"] for e in edges if e.get("condition") == branch), None)
        elif kind == "send_email":
            cfg = node.get("config") or {}
            outbox = OutboxMessage(tenant_id=enrollment.tenant_id, channel="email", recipient=lead.email, subject=_render(cfg.get("subject", ""), lead), body=_render(cfg.get("body", ""), lead), html_body=_render(cfg.get("body", ""), lead), metadata_={"tenant_id": str(enrollment.tenant_id), "lead_id": str(lead.id), "flow_enrollment_id": str(enrollment.id), "asset_ids": cfg.get("asset_ids", [])}, status="pending", priority=5, max_retries=int((version.settings or {}).get("max_retries", 5)))
            db.add(outbox); db.flush(); output = {"outbox_id": str(outbox.id)}
            decision = {"outcome": "queued"}
        elif kind == "intake_prescreen":
            profile = dict(lead.profile_data or {})
            eligible, legacy_reason, snapshot = lead_eligibility(lead)
            duplicate_count = db.query(Lead).filter(Lead.tenant_id == enrollment.tenant_id, Lead.email == lead.email, Lead.id != lead.id, ~Lead.status.in_(("disqualified", "converted", "lost"))).count()
            contact_basis = str(profile.get("contact_basis") or "").lower()
            consent = profile.get("marketing_consent")
            missing_fields = [field for field in ("product_interest",) if not profile.get(field)]
            if duplicate_count or profile.get("ambiguous_duplicate"):
                outcome = "human_review_required"
            elif not eligible:
                outcome = "not_contactable" if legacy_reason in {"missing_valid_email", "suppressed", "marketing_consent_denied"} else "human_review_required"
            elif consent is not True and contact_basis not in {"inbound_request", "existing_business_relationship", "referral_with_consent"}:
                outcome = "consent_missing"
            elif profile.get("product_in_scope") is False:
                outcome = "out_of_scope"
            elif missing_fields:
                outcome = "needs_more_information"
            else:
                outcome = "ready_for_contact"
            allowed = set((node.get("config") or {}).get("allowed_outcomes") or [])
            if outcome not in allowed:
                outcome = "human_review_required"
            output, decision = {"outcome": outcome, "missing_fields": missing_fields, "duplicate_count": duplicate_count, "eligibility_snapshot": snapshot, "contact_basis": contact_basis or None}, {"outcome": outcome}
            if outcome in {"needs_more_information", "consent_missing"}:
                enrollment.status, enrollment.next_run_at = "waiting_input", None
            elif outcome == "human_review_required":
                instance = db.query(TenantWorkflowInstance).filter_by(flow_id=enrollment.flow_id, tenant_id=enrollment.tenant_id).first()
                assignee = db.query(User).filter(User.tenant_id == enrollment.tenant_id, User.is_active.is_(True)).order_by(User.created_at).first()
                sla_due_at = now + timedelta(hours=4)
                task = AgentTask(tenant_id=enrollment.tenant_id, assigned_by=assignee.id if assignee else None, task_type="insurance_prescreen_review", title="Review insurance lead pre-screen", payload={"lead_id": str(lead.id), "enrollment_id": str(enrollment.id), "outcome": output}, status="queued", due_at=sla_due_at)
                db.add(task); db.flush()
                approval = WorkflowApproval(tenant_id=enrollment.tenant_id, workflow_instance_id=instance.id if instance else None, enrollment_id=enrollment.id, node_key=node["key"], node_id=node.get("id"), action="insurance_prescreen_review", task_id=task.id, assigned_to=assignee.id if assignee else None, sla_due_at=sla_due_at, notification_status="queued", requested_payload=output, decision_metadata={})
                db.add(approval); db.flush()
                output.update({"approval_id": str(approval.id), "task_id": str(task.id), "sla_due_at": sla_due_at.isoformat()})
                enrollment.status, enrollment.next_run_at = "waiting_approval", None
            elif outcome != "ready_for_contact":
                enrollment.status, enrollment.stop_reason, enrollment.completed_at = "stopped", f"prescreen:{outcome}", now
        elif kind == "event_branch":
            event_record = (context.get("events") or {}).get(node["key"])
            event = event_record.get("outcome") if isinstance(event_record, dict) else event_record
            event_payload = dict(event_record.get("payload") or {}) if isinstance(event_record, dict) else {}
            allowed = set((node.get("config") or {}).get("allowed_events") or [])
            if event not in allowed:
                enrollment.status, enrollment.next_run_at = "waiting_event", None
                continue
            output, decision = {"event": event, **event_payload}, {"outcome": event}
            profile_updates: dict = {}
            if node["key"] == "first_contact":
                profile_updates = {"product_interest": event_payload.get("product_interest"), "contact_consent": event_payload.get("consent_to_continue"), "urgency": event_payload.get("urgency"), "objections": event_payload.get("objections"), "qualification_evidence": event_payload.get("qualification_evidence")}
            elif node["key"] == "discovery_outcome" and isinstance(event_payload.get("needs_profile"), dict):
                profile_updates = dict(event_payload["needs_profile"])
            if any(value not in (None, "", [], {}) for value in profile_updates.values()):
                lead.profile_data = {**dict(lead.profile_data or {}), **{key: value for key, value in profile_updates.items() if value not in (None, "", [], {})}}
            if event in {"connected_busy", "no_answer", "not_interested", "requests_human", "licensed_agent_required"}:
                context["halt_parent_on_completion"] = event
            next_key = next((e["target"] for e in edges if e.get("condition") == event), None)
        elif kind == "customer_route":
            existing = db.query(Customer).filter(Customer.tenant_id == enrollment.tenant_id, Customer.lead_id == lead.id).first()
            outcome = "existing_customer" if existing else "new_lead"
            output, decision = {"outcome": outcome, "customer_id": str(existing.id) if existing else None}, {"outcome": outcome}
            next_key = next((e["target"] for e in edges if e.get("condition") == outcome), None)
            if outcome != "new_lead":
                enrollment.status, enrollment.stop_reason, enrollment.completed_at = "stopped", "existing_customer_out_of_slice", now
        elif kind == "document_check":
            profile = dict(lead.profile_data or {})
            missing = [field for field in (node.get("config") or {}).get("required_fields", []) if not profile.get(field)]
            output, decision = {"missing_fields": missing}, {"outcome": "missing_documents" if missing else "ready"}
            if missing:
                enrollment.status, enrollment.next_run_at = "waiting_documents", None
        elif kind == "create_task":
            cfg = node.get("config") or {}
            event_payloads = [value.get("payload") for value in (context.get("events") or {}).values() if isinstance(value, dict)]
            callback = next((value for value in reversed(event_payloads) if value and value.get("preferred_callback_at")), {})
            try:
                due_at = datetime.fromisoformat(str(callback.get("preferred_callback_at"))) if callback else now + timedelta(hours=24)
            except ValueError:
                due_at = now + timedelta(hours=24)
            task = AgentTask(tenant_id=enrollment.tenant_id, task_type=cfg.get("task_type", "workflow_followup"), title=node.get("label") or "Workflow follow-up", payload={"lead_id": str(lead.id), "enrollment_id": str(enrollment.id), "context": callback}, status="queued", due_at=due_at)
            db.add(task); db.flush()
            output, decision = {"task_id": str(task.id), "due_at": due_at.isoformat()}, {"outcome": "task_queued"}
        elif kind in {"approval_gate", "handoff"}:
            instance = db.query(TenantWorkflowInstance).filter_by(flow_id=enrollment.flow_id, tenant_id=enrollment.tenant_id).first()
            cfg = node.get("config") or {}
            assignee = db.query(User).filter(User.tenant_id == enrollment.tenant_id, User.is_active.is_(True)).order_by(User.created_at).first()
            sla_due_at = now + timedelta(hours=max(1, int(cfg.get("sla_hours", 4))))
            task = AgentTask(tenant_id=enrollment.tenant_id, assigned_by=assignee.id if assignee else None, task_type=cfg.get("action", "human_handoff"), title=f"Human review: {node.get('label') or node['key']}", payload={"lead_id": str(lead.id), "enrollment_id": str(enrollment.id), "node_outputs": dict(context.get("node_outputs") or {})}, status="queued", due_at=sla_due_at)
            db.add(task); db.flush()
            approval = WorkflowApproval(tenant_id=enrollment.tenant_id, workflow_instance_id=instance.id if instance else None, enrollment_id=enrollment.id, node_key=node["key"], node_id=node.get("id"), action=cfg.get("action", "human_handoff"), task_id=task.id, assigned_to=assignee.id if assignee else None, sla_due_at=sla_due_at, notification_status="queued", requested_payload={"lead_id": str(lead.id), "flow_version_id": str(version.id), "node_output": dict(context.get("node_outputs") or {})}, decision_metadata={})
            db.add(approval); db.flush()
            output, decision = {"approval_id": str(approval.id), "approval_public_id": approval.public_id, "task_id": str(task.id), "assigned_to": str(assignee.id) if assignee else None, "sla_due_at": sla_due_at.isoformat()}, {"outcome": "pending_human_approval"}
            enrollment.status, enrollment.next_run_at = "waiting_approval", None
        elif kind == "subflow":
            child_flow_id = (node.get("config") or {}).get("child_flow_id")
            if not child_flow_id:
                if (node.get("config") or {}).get("optional"):
                    output, decision = {"skipped": True}, {"outcome": "optional_slot_skipped"}
                else:
                    enrollment.status, enrollment.stop_reason, enrollment.completed_at = "stopped", "subflow_not_configured", now
            else:
                child_flow = db.get(FlowDefinition, UUID(str(child_flow_id)))
                child_version = (db.get(FlowVersion, child_flow.active_version_id) if child_flow and child_flow.active_version_id else None) or (db.query(FlowVersion).filter_by(flow_id=child_flow.id).order_by(FlowVersion.version.desc()).first() if child_flow else None)
                child_trigger = next((item for item in (child_version.graph if child_version else {}).get("nodes", []) if item.get("type") == "trigger"), None)
                if not child_version or not child_trigger:
                    enrollment.status, enrollment.stop_reason, enrollment.completed_at = "stopped", "invalid_child_subflow", now
                else:
                    child = FlowEnrollment(tenant_id=enrollment.tenant_id, flow_id=child_flow.id, flow_version_id=child_version.id, lead_id=lead.id, status="running", current_node_key=child_trigger["key"], current_node_id=child_trigger.get("id"), next_run_at=now, context={"source": "subflow", "node_runs": {}, "parent_enrollment_id": str(enrollment.id)}, enrollment_source="subflow", eligibility_snapshot=dict(enrollment.eligibility_snapshot or {}), parent_enrollment_id=enrollment.id, parent_node_key=node["key"])
                    db.add(child); db.flush()
                    output, decision = {"child_enrollment_id": str(child.id)}, {"outcome": "child_started"}
                    enrollment.status, enrollment.next_run_at = "waiting_child", None
        elif kind == "stop":
            enrollment.status, enrollment.completed_at, enrollment.stop_reason = "completed", now, "flow_complete"
        if next_key is None and edges: next_key = edges[0]["target"]
        runs[node["key"]] = attempt; context["node_runs"] = runs
        node_outputs = dict(context.get("node_outputs") or {}); node_outputs[node["key"]] = output; context["node_outputs"] = node_outputs; enrollment.context = context
        verification = {"execution_recorded": True, "status": enrollment.status}
        if kind == "send_email": verification.update({"outbox_persisted": bool(output.get("outbox_id"))})
        elif kind == "intake_prescreen": verification.update({"lead_persisted": True, "tenant_scoped": True, "contactability_outcome": output.get("outcome")})
        elif kind == "event_branch": verification.update({"event_allowlisted": True, "required_payload_present": True, "contact_receipt_present": bool(output.get("contact_receipt_id")) if node["key"] == "first_contact" else None, "citations_present": bool(output.get("citations")) if node["key"] == "discovery_outcome" else None})
        elif kind == "document_check": verification.update({"required_fields_present": not bool(output.get("missing_fields")), "missing_fields": output.get("missing_fields", [])})
        elif kind in {"approval_gate", "handoff"}: verification.update({"approval_recorded": bool(output.get("approval_id")), "task_recorded": bool(output.get("task_id")), "sla_started": bool(output.get("sla_due_at"))})
        node_contract = dict((workflow_template.node_contracts or {}).get(node["key"]) or {}) if workflow_template else {}
        if not node_contract and workflow_instance:
            node_contract = next((dict(raw.get("contract") or {}) for raw in (workflow_instance.overrides or {}).get("added_nodes", []) if raw.get("key") == node["key"]), {})
        audit_metadata = {"flow_version_id": str(version.id), "flow_version": version.version, "workflow_instance_id": str(workflow_instance.id) if workflow_instance else None, "workflow_template_id": str(workflow_template.id) if workflow_template else None, "workflow_template_slug": workflow_template.slug if workflow_template else None, "workflow_template_version": workflow_template.version if workflow_template else None, "node_id": node.get("id"), "node_contract": node_contract, "decision_source": "allowlisted_external_event" if kind == "event_branch" else "deterministic_code", "model_version": output.get("model_version"), "conversation_id": output.get("conversation_id"), "citations": output.get("citations", []), "contact_receipt_id": output.get("contact_receipt_id")}
        db.add(FlowExecutionStep(tenant_id=enrollment.tenant_id, enrollment_id=enrollment.id, lead_id=lead.id, node_key=node["key"], node_id=node.get("id"), action_type=kind, attempt=attempt, idempotency_key=idempotency, status="completed", output=output, decision=decision, verification=verification, audit_metadata=audit_metadata, completed_at=now))
        try:
            from app.services.knowledge.memory_store import append_lead_flow_event
            append_lead_flow_event(tenant_id=str(enrollment.tenant_id), lead_id=str(lead.id), enrollment_id=str(enrollment.id), node_key=node["key"], event_type=kind, data={"attempt": attempt, **output})
        except Exception:
            pass
        if enrollment.status not in ("completed", "stopped", "waiting_approval", "waiting_child", "waiting_documents", "waiting_input", "waiting_event"):
            if next_key:
                enrollment.current_node_key = next_key
                next_node = next((item for item in graph.get("nodes", []) if item.get("key") == next_key), None)
                enrollment.current_node_id = next_node.get("id") if next_node else None
            else: enrollment.status, enrollment.completed_at, enrollment.stop_reason = "completed", now, "no_next_node"
        if enrollment.status in ("completed", "stopped") and enrollment.parent_enrollment_id:
            parent = db.get(FlowEnrollment, enrollment.parent_enrollment_id)
            if parent and parent.status == "waiting_child":
                parent_context = dict(parent.context or {})
                child_outputs = dict(parent_context.get("child_outputs") or {})
                child_outputs[parent.current_node_key] = {"status": enrollment.status, "stop_reason": enrollment.stop_reason, "node_outputs": dict((enrollment.context or {}).get("node_outputs") or {})}
                parent_context["child_outputs"] = child_outputs
                parent.context = parent_context
                if enrollment.status == "stopped":
                    parent.status, parent.completed_at, parent.stop_reason = "stopped", now, f"child:{enrollment.stop_reason or 'stopped'}"
                    processed += 1
                    continue
                halt_outcome = (enrollment.context or {}).get("halt_parent_on_completion")
                if halt_outcome:
                    parent.status, parent.completed_at, parent.stop_reason = "stopped", now, f"engagement:{halt_outcome}"
                    processed += 1
                    continue
                parent_version = db.get(FlowVersion, parent.flow_version_id)
                parent_edges = [edge for edge in (parent_version.graph or {}).get("edges", []) if edge.get("source") == parent.current_node_key]
                parent_next = parent_edges[0].get("target") if parent_edges else None
                if parent_next:
                    parent.current_node_key, parent.status, parent.next_run_at = parent_next, "running", now
                    parent_node = next((item for item in (parent_version.graph or {}).get("nodes", []) if item.get("key") == parent_next), None)
                    parent.current_node_id = parent_node.get("id") if parent_node else None
                else:
                    parent.status, parent.completed_at, parent.stop_reason = "completed", now, "child_flow_complete"
        processed += 1
    db.commit()
    return processed
