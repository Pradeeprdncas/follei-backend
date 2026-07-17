"""Unit tests for PromptRegistry."""
import pytest
from mcp.registry.prompts import PromptRegistry, Prompt, PromptArgument


@pytest.mark.asyncio
async def test_prompt_registry_operations() -> None:
    registry = PromptRegistry()

    async def mock_handler(args: dict) -> list:
        name = args.get("name", "Guest")
        return [{"role": "user", "content": {"type": "text", "text": f"Hello {name}"}}]

    prompt = Prompt(
        name="greet",
        description="Greets a user",
        arguments=[PromptArgument(name="name", description="The name", required=True)]
    )

    # Register
    await registry.register_prompt(prompt, mock_handler)

    # List
    items = await registry.list_prompts()
    assert len(items) == 1
    assert items[0].name == "greet"

    # Get
    messages = await registry.get_prompt("greet", {"name": "Alice"})
    assert len(messages) == 1
    assert messages[0]["content"]["text"] == "Hello Alice"

    # Get invalid
    with pytest.raises(KeyError):
        await registry.get_prompt("invalid", {})

    # Unregister
    await registry.unregister_prompt("greet")
    items_after = await registry.list_prompts()
    assert len(items_after) == 0
