"""Tool registry — decorator-based registration with Pydantic-derived schemas.

Per CLAUDE.md: tool schemas are defined as Pydantic models and converted to
JSON Schema automatically. Never hand-write tool JSON schemas.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from aiops_agent.llm import ToolSpec

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT")


class ToolHandler(Generic[InputT, OutputT]):
    """Runtime container pairing a callable with its Pydantic input model."""

    def __init__(
        self,
        name: str,
        description: str,
        input_model: type[InputT],
        func: Callable[[InputT], OutputT],
    ) -> None:
        self.name = name
        self.description = description
        self.input_model = input_model
        self.func = func

    def spec(self) -> ToolSpec:
        """Render as a ToolSpec for the LLM."""
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=self.input_model.model_json_schema(),
        )

    def invoke(self, raw_input: dict[str, Any]) -> OutputT:
        """Validate raw LLM-provided input, then call the underlying function."""
        validated = self.input_model.model_validate(raw_input)
        return self.func(validated)


_REGISTRY: dict[str, ToolHandler[Any, Any]] = {}


def register_tool(
    input_model: type[InputT],
    *,
    name: str | None = None,
) -> Callable[[Callable[[InputT], OutputT]], Callable[[InputT], OutputT]]:
    """Register a function as an LLM-callable tool.

    Args:
        input_model: Pydantic model describing the tool's input schema.
        name: Override the tool name (defaults to the function name).
    """

    def decorator(
        func: Callable[[InputT], OutputT],
    ) -> Callable[[InputT], OutputT]:
        tool_name = name or func.__name__
        if tool_name in _REGISTRY:
            raise ValueError(f"Tool already registered: {tool_name}")
        description = inspect.getdoc(func)
        if not description:
            raise ValueError(
                f"Tool {tool_name!r} is missing a docstring; the LLM relies on "
                "it to decide when to invoke the tool."
            )
        _REGISTRY[tool_name] = ToolHandler(
            name=tool_name,
            description=description,
            input_model=input_model,
            func=func,
        )
        return func

    return decorator


def get_tool_specs() -> list[ToolSpec]:
    """Return all registered tools as ToolSpecs for an LLM request."""
    return [h.spec() for h in _REGISTRY.values()]


def resolve_tool(name: str) -> ToolHandler[Any, Any]:
    """Look up a registered tool by name."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown tool: {name!r}") from exc
