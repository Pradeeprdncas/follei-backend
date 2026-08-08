from types import SimpleNamespace

from app.services.knowledge.categories import CATEGORY_DEFINITIONS, MANDATORY_GROUPS
from app.services.onboarding_state import evaluate_readiness


def _category_rows() -> list[dict[str, object]]:
    return [
        {
            "key": definition.key,
            "mandatory_group": definition.mandatory_group,
            "status": "missing",
            "count": 0,
        }
        for definition in CATEGORY_DEFINITIONS
    ]


def test_any_one_populated_category_satisfies_each_mandatory_group_across_25_categories():
    categories = _category_rows()
    assert len(categories) == 25
    selected = {accepted_categories[0] for accepted_categories in MANDATORY_GROUPS.values()}
    for category in categories:
        if category["key"] in selected:
            category["status"] = "found"
            category["count"] = 1

    readiness = evaluate_readiness(categories, {}, [])

    assert readiness["missing_groups"] == []
    assert readiness["confirmations_needed"] == []
    assert readiness["can_continue"] is True
    assert readiness["ready_for_autonomous_actions"] is True


def test_can_continue_is_false_when_a_mandatory_group_is_empty_and_unconfirmed():
    categories = _category_rows()
    for group, accepted_categories in MANDATORY_GROUPS.items():
        if group == "governance":
            continue
        selected = accepted_categories[0]
        category = next(item for item in categories if item["key"] == selected)
        category["status"] = "partial"
        category["count"] = 1

    readiness = evaluate_readiness(categories, {}, [])

    assert readiness["missing_groups"] == ["governance"]
    assert readiness["confirmations_needed"] == ["governance"]
    assert readiness["can_continue"] is False
    assert readiness["ready_for_autonomous_actions"] is False

    confirmed = evaluate_readiness(
        categories,
        {"governance": SimpleNamespace(resolution="not_applicable")},
        [],
    )
    assert confirmed["confirmations_needed"] == []
    assert confirmed["can_continue"] is True
    assert confirmed["ready_for_autonomous_actions"] is False
