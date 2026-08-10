"""Execution-backed smoke tests for the two knowledge projection stores."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.config.ferretdb import get_context_database


@pytest.mark.integration
def test_live_ferretdb_round_trip_is_tenant_scoped() -> None:
    collection = get_context_database()["runtime_smoke_test"]
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    marker = str(uuid4())
    try:
        collection.insert_many(
            [
                {"tenant_id": tenant_a, "marker": marker, "text": "tenant A"},
                {"tenant_id": tenant_b, "marker": marker, "text": "tenant B"},
            ]
        )
        rows = list(collection.find({"tenant_id": tenant_a, "marker": marker}))
        assert [row["text"] for row in rows] == ["tenant A"]
    finally:
        collection.delete_many({"marker": marker})
