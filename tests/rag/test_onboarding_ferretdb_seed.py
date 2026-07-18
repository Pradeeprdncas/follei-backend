"""Onboarding item 8 regression: seed FerretDB tenant-level context from onboarding answers."""
from app.services.knowledge import memory_store
from app.services.knowledge.orchestrator import _decorate


class _Collection:
    def __init__(self):
        self.rows = {}

    def find_one(self, key, projection=None):
        return self.rows.get((key["tenant_id"], key["subject_type"], key["subject_id"]))

    def replace_one(self, key, value, upsert=False):
        self.rows[(key["tenant_id"], key["subject_type"], key["subject_id"])] = value


def test_seed_writes_tenant_level_context(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(memory_store, "get_context_database", lambda: {"tenant_context": collection})

    doc = memory_store.seed_onboarding_context(
        tenant_id="tenant-a", industry="SaaS", goals=["Increase Revenue", "Reduce Customer Churn"], contact_channels=["Email", "WhatsApp"],
    )
    assert doc["industry"] == "SaaS"
    assert doc["goals"] == ["Increase Revenue", "Reduce Customer Churn"]
    assert doc["contact_channels"] == ["Email", "WhatsApp"]
    assert doc["seeded_from"] == "onboarding"
    assert ("tenant-a", "tenant", "tenant-a") in collection.rows


def test_seed_is_idempotent_and_overwrites_prior_seed(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(memory_store, "get_context_database", lambda: {"tenant_context": collection})

    memory_store.seed_onboarding_context(tenant_id="tenant-a", industry="SaaS", goals=["Increase Revenue"], contact_channels=["Email"])
    second = memory_store.seed_onboarding_context(tenant_id="tenant-a", industry="Healthcare", goals=["Reduce Customer Churn"], contact_channels=["Phone"])

    assert second["industry"] == "Healthcare"
    assert len(collection.rows) == 1


def test_seeded_context_is_readable_via_the_orchestrator_decoration(monkeypatch):
    """This is exactly the shape build_agent_context() decorates as customer_context."""
    collection = _Collection()
    monkeypatch.setattr(memory_store, "get_context_database", lambda: {"tenant_context": collection})
    memory_store.seed_onboarding_context(tenant_id="tenant-a", industry="SaaS", goals=["Track Customer Health"], contact_channels=["SMS"])

    from app.services.knowledge import context_store
    monkeypatch.setattr(context_store, "get_context_database", lambda: {"tenant_context": collection})
    raw = context_store.get_context(tenant_id="tenant-a", subject_type="tenant", subject_id="tenant-a")
    assert raw["industry"] == "SaaS"

    decorated = _decorate(raw, source="ferret", updated_at=raw.get("updated_at"))
    assert decorated["source"] == "ferret"
    assert decorated["industry"] == "SaaS"
