"""Unit tests for the tool layer: decorator introspection, registry, soft failures."""

import pytest

from facets.agents import ExecutionContext
from facets.tools import ToolRegistry, tool


@tool
async def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@tool(name="greet", description="Greet someone.")
async def _greet(name: str, excited: bool = False) -> str:
    return f"Hello, {name}{'!' if excited else '.'}"


@tool
async def boom() -> str:
    """Always raises."""
    raise ValueError("kaboom")


def test_decorator_infers_schema_and_required():
    spec = add.spec
    assert spec.name == "add"
    assert spec.description == "Add two integers."
    assert spec.parameters["properties"]["a"] == {"type": "integer"}
    assert set(spec.parameters["required"]) == {"a", "b"}


def test_decorator_optional_param_not_required():
    spec = _greet.spec
    assert spec.name == "greet"
    assert spec.parameters["required"] == ["name"]  # excited has a default
    assert spec.parameters["properties"]["excited"] == {"type": "boolean"}


def test_openai_rendering_shape():
    rendered = add.spec.to_openai()
    assert rendered["type"] == "function"
    assert rendered["function"]["name"] == "add"


async def test_execute_success():
    ctx = ExecutionContext(task_id="t")
    result = await add.execute({"a": 2, "b": 3}, ctx)
    assert result.content == 5
    assert not result.is_error


async def test_execute_failure_is_soft():
    ctx = ExecutionContext(task_id="t")
    result = await boom.execute({}, ctx)
    assert result.is_error
    assert "kaboom" in result.content


def test_registry_lookup_and_specs():
    reg = ToolRegistry([add, _greet])
    assert len(reg) == 2
    assert "add" in reg
    assert reg.get("greet") is _greet
    assert set(reg.names()) == {"add", "greet"}
    assert len(reg.openai_tools()) == 2


@pytest.mark.parametrize("bad", ["missing", "nope"])
def test_registry_missing_returns_none(bad):
    reg = ToolRegistry([add])
    assert reg.get(bad) is None
