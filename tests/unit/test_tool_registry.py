"""Tool registry: decorator-based registration and schema derivation."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from aiops_agent.tools.registry import (
    _REGISTRY,
    get_tool_specs,
    register_tool,
    resolve_tool,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    snapshot = dict(_REGISTRY)
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)


class _Input(BaseModel):
    host: str = Field(description="Target hostname")
    limit: int = Field(default=10, ge=1)


def test_register_and_invoke_tool() -> None:
    @register_tool(_Input)
    def list_alerts(payload: _Input) -> dict[str, object]:
        """List recent alerts for a host."""
        return {"host": payload.host, "limit": payload.limit, "alerts": []}

    handler = resolve_tool("list_alerts")
    result = handler.invoke({"host": "api-1", "limit": 5})
    assert result == {"host": "api-1", "limit": 5, "alerts": []}


def test_spec_includes_schema_and_docstring() -> None:
    @register_tool(_Input)
    def list_alerts(payload: _Input) -> str:
        """List recent alerts for a host."""
        return "ok"

    specs = get_tool_specs()
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "list_alerts"
    assert spec.description == "List recent alerts for a host."
    assert spec.input_schema["properties"]["host"]["type"] == "string"


def test_missing_docstring_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing a docstring"):

        @register_tool(_Input)
        def no_doc(payload: _Input) -> str:
            return "x"


def test_duplicate_registration_is_rejected() -> None:
    @register_tool(_Input)
    def dup(payload: _Input) -> str:
        """First."""
        return "x"

    with pytest.raises(ValueError, match="already registered"):

        @register_tool(_Input, name="dup")
        def dup2(payload: _Input) -> str:
            """Second."""
            return "y"
