"""Tools surfaced to the LLM.

Adding a tool:

1. Create a module under `aiops_agent/tools/<tool_name>.py` exporting a
   callable plus a Pydantic input model.
2. Wrap it with `@register_tool(InputModel)` — this auto-derives the JSON
   Schema from the model and uses the function docstring as the LLM-facing
   description.
3. Import the module below so it registers on package import.
4. Add a unit test under `tests/unit/tools/test_<tool_name>.py`.
"""

from aiops_agent.tools.registry import (
    ToolHandler,
    get_tool_specs,
    register_tool,
    resolve_tool,
)

__all__ = [
    "ToolHandler",
    "get_tool_specs",
    "register_tool",
    "resolve_tool",
]
