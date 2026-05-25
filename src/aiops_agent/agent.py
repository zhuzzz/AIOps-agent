"""Core agent loop: observe → think → act → observe.

The loop:

1. Send the conversation + tool surface to the LLM.
2. If the model returns `stop_reason == "tool_use"`, execute each tool call
   via the registry, append `tool_result` blocks, and loop.
3. If the model returns `stop_reason == "end_turn"`, return the final text.
4. Guard against runaway loops with `Settings.max_iterations`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from anthropic.types import MessageParam

from aiops_agent.config import Settings, get_settings
from aiops_agent.llm import LLMClient
from aiops_agent.prompts import load_prompt
from aiops_agent.tools import get_tool_specs, resolve_tool
from aiops_agent.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AgentResult:
    """Outcome of one agent invocation."""

    final_text: str
    iterations: int
    stop_reason: str


class Agent:
    """Orchestrates the LLM <-> tools loop for a single task."""

    def __init__(
        self,
        *,
        llm: LLMClient | None = None,
        settings: Settings | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._llm = llm or LLMClient(self._settings)
        self._system_prompt = system_prompt or load_prompt("system.txt")

    def run(self, task: str) -> AgentResult:
        """Run the agent loop against a single user task."""
        messages: list[MessageParam] = [{"role": "user", "content": task}]
        tool_specs = get_tool_specs()

        for iteration in range(1, self._settings.max_iterations + 1):
            logger.info("agent.iteration", n=iteration)
            response = self._llm.create_message(
                messages=messages,
                system=self._system_prompt,
                tools=tool_specs or None,
                adaptive_thinking=True,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                final_text = _extract_text(response.content)
                return AgentResult(
                    final_text=final_text,
                    iterations=iteration,
                    stop_reason=response.stop_reason or "end_turn",
                )

            tool_results = _run_tool_calls(response.content)
            messages.append(
                cast(MessageParam, {"role": "user", "content": tool_results})
            )

        logger.warning(
            "agent.max_iterations_reached",
            max_iterations=self._settings.max_iterations,
        )
        return AgentResult(
            final_text="[Agent stopped: max iterations reached]",
            iterations=self._settings.max_iterations,
            stop_reason="max_iterations",
        )


def _extract_text(blocks: list[Any]) -> str:
    """Concatenate all text blocks from an assistant response."""
    parts: list[str] = []
    for block in blocks:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts)


def _run_tool_calls(blocks: list[Any]) -> list[dict[str, Any]]:
    """Execute every `tool_use` block and produce matching `tool_result` blocks."""
    results: list[dict[str, Any]] = []
    for block in blocks:
        if getattr(block, "type", None) != "tool_use":
            continue
        handler = resolve_tool(block.name)
        try:
            output = handler.invoke(block.input)
            content = (
                output if isinstance(output, str) else json.dumps(output, default=str)
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                }
            )
        except Exception as exc:
            logger.exception("agent.tool_failure", tool=block.name)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Tool {block.name} failed: {exc}",
                    "is_error": True,
                }
            )
    return results
