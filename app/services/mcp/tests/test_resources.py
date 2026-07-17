"""Unit tests for ResourceRegistry."""
import pytest
from mcp.registry.resources import ResourceRegistry, Resource


@pytest.mark.asyncio
async def test_resource_registry_operations() -> None:
    registry = ResourceRegistry()

    # Define resolver mock handler
    async def mock_handler(uri: str) -> str:
        return f"Content of {uri}"

    res = Resource(
        uri="test://resource",
        name="Test Resource",
        description="A mock test resource",
        mimeType="text/plain"
    )

    # Register
    await registry.register_resource(res, mock_handler)

    # List
    items = await registry.list_resources()
    assert len(items) == 1
    assert items[0].uri == "test://resource"
    assert items[0].mimeType == "text/plain"

    # Read
    content = await registry.read_resource("test://resource")
    assert content == "Content of test://resource"

    # Read invalid
    with pytest.raises(KeyError):
        await registry.read_resource("test://invalid")

    # Unregister
    await registry.unregister_resource("test://resource")
    items_after = await registry.list_resources()
    assert len(items_after) == 0
