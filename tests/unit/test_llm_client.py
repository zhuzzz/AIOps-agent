"""LLM client wrapper: request shaping and response surfacing.

External HTTP calls are mocked with respx so tests run hermetically.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from aiops_agent.llm import LLMClient, ToolSpec


_API_URL = "https://api.anthropic.com/v1/messages"


def _ok_response(stop_reason: str = "end_turn") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "hi"}],
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 5,
                "output_tokens": 2,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        },
    )


@respx.mock
def test_create_message_sets_required_fields() -> None:
    route = respx.post(_API_URL).mock(return_value=_ok_response())

    client = LLMClient()
    response = client.create_message(
        messages=[{"role": "user", "content": "hello"}],
        system="be brief",
    )

    assert response.stop_reason == "end_turn"
    request_body = route.calls.last.request.read().decode()
    assert '"model":"claude-sonnet-4-6"' in request_body
    assert '"max_tokens":16000' in request_body
    assert '"system":"be brief"' in request_body


@respx.mock
def test_create_message_includes_tools_and_adaptive_thinking() -> None:
    route = respx.post(_API_URL).mock(return_value=_ok_response())

    tool = ToolSpec(
        name="ping",
        description="Ping a host",
        input_schema={"type": "object", "properties": {}},
    )
    LLMClient().create_message(
        messages=[{"role": "user", "content": "do it"}],
        tools=[tool],
        adaptive_thinking=True,
        max_tokens=8192,
        model="claude-haiku-4-5-20251001",
    )

    body = route.calls.last.request.read().decode()
    assert '"max_tokens":8192' in body
    assert '"model":"claude-haiku-4-5-20251001"' in body
    assert '"thinking":{"type":"adaptive"}' in body
    assert '"name":"ping"' in body


@respx.mock
def test_create_message_propagates_api_errors() -> None:
    respx.post(_API_URL).mock(
        return_value=httpx.Response(
            400,
            json={
                "type": "error",
                "error": {"type": "invalid_request_error", "message": "bad"},
            },
        )
    )

    import anthropic

    with pytest.raises(anthropic.BadRequestError):
        LLMClient().create_message(
            messages=[{"role": "user", "content": "hello"}],
        )
