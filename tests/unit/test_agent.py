"""Agent loop: tool dispatch and termination."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel

from aiops_agent.agent import Agent
from aiops_agent.tools.registry import _REGISTRY, register_tool


@dataclass
class _StubBlock:
    type: str
    text: str = ""
    name: str = ""
    id: str = ""
    input: dict[str, Any] | None = None


@dataclass
class _StubUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class _StubResponse:
    content: list[_StubBlock]
    stop_reason: str
    usage: _StubUsage


class _StubLLM:
    """LLM stub that replays a scripted sequence of responses."""

    def __init__(self, responses: list[_StubResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create_message(self, **kwargs: Any) -> _StubResponse:
        # Deep-copy messages so the recorded call reflects state at call time,
        # not after the agent has appended subsequent turns.
        import copy

        self.calls.append({**kwargs, "messages": copy.deepcopy(kwargs["messages"])})
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def _clear_registry():
    snapshot = dict(_REGISTRY)
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)


class _PingInput(BaseModel):
    host: str


def test_agent_executes_tool_then_terminates() -> None:
    @register_tool(_PingInput)
    def ping(payload: _PingInput) -> str:
        """Ping a host."""
        return f"pong:{payload.host}"

    llm = _StubLLM(
        [
            _StubResponse(
                content=[
                    _StubBlock(
                        type="tool_use", name="ping", id="tu_1", input={"host": "a"}
                    ),
                ],
                stop_reason="tool_use",
                usage=_StubUsage(),
            ),
            _StubResponse(
                content=[_StubBlock(type="text", text="Done.")],
                stop_reason="end_turn",
                usage=_StubUsage(),
            ),
        ]
    )

    agent = Agent(llm=llm)  # type: ignore[arg-type]
    result = agent.run("check host a")

    assert result.final_text == "Done."
    assert result.iterations == 2
    assert result.stop_reason == "end_turn"
    assert len(llm.calls) == 2

    # Second call must contain the tool_result with the actual tool output.
    second_messages = llm.calls[1]["messages"]
    tool_result_msg = second_messages[-1]
    assert tool_result_msg["role"] == "user"
    assert tool_result_msg["content"][0]["content"] == "pong:a"


def test_agent_surfaces_tool_errors_to_model() -> None:
    @register_tool(_PingInput)
    def ping(payload: _PingInput) -> str:
        """Ping a host."""
        raise RuntimeError("network down")

    llm = _StubLLM(
        [
            _StubResponse(
                content=[
                    _StubBlock(
                        type="tool_use", name="ping", id="tu_1", input={"host": "a"}
                    ),
                ],
                stop_reason="tool_use",
                usage=_StubUsage(),
            ),
            _StubResponse(
                content=[_StubBlock(type="text", text="Reporting failure.")],
                stop_reason="end_turn",
                usage=_StubUsage(),
            ),
        ]
    )

    result = Agent(llm=llm).run("check host a")  # type: ignore[arg-type]
    assert result.stop_reason == "end_turn"

    tool_result = llm.calls[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert "network down" in tool_result["content"]


def test_agent_stops_at_max_iterations(env_with) -> None:
    env_with(AIOPS_MAX_ITERATIONS="2")

    @register_tool(_PingInput)
    def ping(payload: _PingInput) -> str:
        """Ping a host."""
        return "ok"

    llm = _StubLLM(
        [
            _StubResponse(
                content=[
                    _StubBlock(
                        type="tool_use", name="ping", id=f"tu_{i}", input={"host": "a"}
                    ),
                ],
                stop_reason="tool_use",
                usage=_StubUsage(),
            )
            for i in range(5)
        ]
    )

    result = Agent(llm=llm).run("loop forever")  # type: ignore[arg-type]
    assert result.stop_reason == "max_iterations"
    assert result.iterations == 2
