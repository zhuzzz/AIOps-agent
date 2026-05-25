"""Settings load from environment variables with expected defaults."""

from __future__ import annotations

from aiops_agent.config import get_settings


def test_defaults_apply_when_only_api_key_is_set() -> None:
    settings = get_settings()
    assert settings.llm_model == "claude-sonnet-4-6"
    assert settings.llm_fast_model == "claude-haiku-4-5-20251001"
    assert settings.llm_max_tokens == 16000
    assert settings.log_level == "DEBUG"
    assert settings.max_iterations == 20
    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-test-fake"


def test_env_overrides_apply(env_with) -> None:
    env_with(
        AIOPS_LLM_MODEL="claude-haiku-4-5-20251001",
        AIOPS_LLM_MAX_TOKENS="4096",
        AIOPS_MAX_ITERATIONS="5",
    )
    settings = get_settings()
    assert settings.llm_model == "claude-haiku-4-5-20251001"
    assert settings.llm_max_tokens == 4096
    assert settings.max_iterations == 5
