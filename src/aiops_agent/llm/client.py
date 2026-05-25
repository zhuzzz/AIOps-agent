"""Thin wrapper around the Anthropic SDK.

This is the only module in the project that imports `anthropic` directly.
It exists to:

1. Enforce that `max_tokens` is always set explicitly.
2. Centralize model selection so feature code never hard-codes model strings.
3. Log every request and response at DEBUG (no secrets, no PII).
4. Rely on the SDK's built-in retry/backoff for 429 / 5xx — no ad-hoc retry
   loops elsewhere in the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import anthropic
from anthropic.types import Message, MessageParam

from aiops_agent.config import Settings, get_settings
from aiops_agent.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ToolSpec:
    """A tool definition surfaced to the LLM.

    Attributes:
        name: Stable identifier the model uses to invoke the tool.
        description: Natural-language description; the model relies on this
            heavily to decide when to call the tool.
        input_schema: JSON Schema describing the tool's input parameters.
    """

    name: str
    description: str
    input_schema: dict[str, Any]

    def to_api_dict(self) -> dict[str, Any]:
        """Render as the dict shape the Anthropic API expects."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class LLMClient:
    """Project-wide chokepoint for Anthropic API calls."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = anthropic.Anthropic(
            api_key=self._settings.anthropic_api_key.get_secret_value(),
            max_retries=3,
        )

    def create_message(
        self,
        *,
        messages: list[MessageParam],
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        adaptive_thinking: bool = False,
    ) -> Message:
        """Send a Messages API request.

        Args:
            messages: Conversation history (user/assistant turns).
            system: Optional system prompt.
            tools: Optional tool surface exposed to the model.
            model: Override the configured default model.
            max_tokens: Override the configured per-call cap.
            adaptive_thinking: Enable adaptive extended thinking. Use for
                multi-step diagnostic / RCA reasoning where the model should
                decide its own thinking depth.

        Returns:
            The Anthropic `Message` response object.
        """
        chosen_model = model or self._settings.llm_model
        chosen_max_tokens = max_tokens or self._settings.llm_max_tokens

        kwargs: dict[str, Any] = {
            "model": chosen_model,
            "max_tokens": chosen_max_tokens,
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [t.to_api_dict() for t in tools]
        if adaptive_thinking:
            kwargs["thinking"] = {"type": "adaptive"}

        logger.debug(
            "llm.request",
            model=chosen_model,
            max_tokens=chosen_max_tokens,
            num_messages=len(messages),
            has_system=system is not None,
            num_tools=len(tools) if tools else 0,
            adaptive_thinking=adaptive_thinking,
        )

        response: Message = self._client.messages.create(**kwargs)

        logger.debug(
            "llm.response",
            model=chosen_model,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_input_tokens=getattr(
                response.usage, "cache_read_input_tokens", 0
            ),
        )

        return response
