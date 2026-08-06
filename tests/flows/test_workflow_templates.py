from app.services.flows.service import (
    insurance_template_spec,
    insurance_child_template_specs,
    universal_template_spec,
    validate_graph,
    validate_node_contracts,
)


def test_universal_template_has_the_seven_tenant_slots_and_contracts():
    spec = universal_template_spec()
    assert [node["id"] for node in spec["graph"]["nodes"]] == [node["id"] for node in universal_template_spec()["graph"]["nodes"]]
    keys = {node["key"] for node in spec["graph"]["nodes"]}
    assert {"intake_identification", "segmentation_routing", "engagement", "preparation_documentation", "handoff_approval", "fulfillment", "ongoing_relationship"} <= keys
    assert validate_graph(spec["graph"], spec["settings"]) == []
    assert validate_node_contracts(spec["graph"], spec["node_contracts"]) == []


def test_insurance_template_is_a_complete_auditable_vertical_slice():
    spec = insurance_template_spec()
    keys = [node["key"] for node in spec["graph"]["nodes"]]
    assert keys == ["start", "intake_prescreen", "first_contact", "plan_nurture", "quote_preparation", "human_handoff", "complete"]
    assert validate_graph(spec["graph"], spec["settings"]) == []
    assert validate_node_contracts(spec["graph"], spec["node_contracts"]) == []
    handoff = next(node for node in spec["graph"]["nodes"] if node["key"] == "human_handoff")
    assert handoff["type"] == "approval_gate"
    assert handoff["config"]["hard_gate"] is True


def test_insurance_pack_fills_the_five_in_scope_universal_slots():
    specs = {spec["slug"]: spec for spec in insurance_child_template_specs()}
    assert set(specs) == {"insurance-intake-prescreen", "insurance-new-lead-routing", "insurance-engagement", "insurance-quote-preparation", "insurance-human-handoff"}
    for spec in specs.values():
        assert validate_graph(spec["graph"], spec["settings"]) == []
        assert validate_node_contracts(spec["graph"], spec["node_contracts"]) == []
        assert spec["settings"]["auto_enroll_new_leads"] is False

    engagement = specs["insurance-engagement"]
    first_contact = next(node for node in engagement["graph"]["nodes"] if node["key"] == "first_contact")
    assert set(first_contact["config"]["allowed_events"]) == {"connected_interested", "connected_busy", "no_answer", "not_interested", "requests_human"}
    assert "contact_receipt_id" in first_contact["config"]["required_payload_by_event"]["connected_interested"]
    assert any(edge.get("condition") == "licensed_agent_required" and edge["target"] == "human_request" for edge in engagement["graph"]["edges"])
