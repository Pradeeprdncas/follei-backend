import pytest

from app.services.knowledge.categories import KnowledgeCategory, normalize_category


@pytest.mark.parametrize("category", [item.value for item in KnowledgeCategory])
def test_every_canonical_category_is_accepted(category):
    assert normalize_category(category) == category


@pytest.mark.parametrize(("legacy", "canonical"), [
    ("product", "products"), ("policy", "policies"),
    ("customer_segment", "customer_segments"), ("sales_process", "sales_processes"),
])
def test_legacy_categories_normalize_at_the_boundary(legacy, canonical):
    assert normalize_category(legacy) == canonical


def test_unknown_category_is_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        normalize_category("medical_diagnosis")
