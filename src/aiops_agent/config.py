"""Application configuration loaded from environment variables.

All settings flow through this module — application code MUST NOT read
`os.environ` directly. Adding a new setting requires both a field here and a
documented entry in `.env.example`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    """Runtime configuration for the AIOps agent."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    anthropic_api_key: SecretStr = Field(
        ...,
        description="Anthropic API key used for all LLM calls.",
    )
    llm_model: str = Field(
        default="claude-sonnet-4-6",
        alias="AIOPS_LLM_MODEL",
        description="Default Claude model for production paths.",
    )
    llm_fast_model: str = Field(
        default="claude-haiku-4-5-20251001",
        alias="AIOPS_LLM_FAST_MODEL",
        description="Lightweight Claude model for fast / cheap paths.",
    )
    llm_max_tokens: int = Field(
        default=16000,
        alias="AIOPS_LLM_MAX_TOKENS",
        ge=1,
        description="Per-call max_tokens cap; never rely on the API default.",
    )
    log_level: LogLevel = Field(default="INFO", alias="AIOPS_LOG_LEVEL")
    max_iterations: int = Field(
        default=20,
        alias="AIOPS_MAX_ITERATIONS",
        ge=1,
        description="Hard cap on agent loop iterations per task.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton.

    Settings are resolved lazily on first access so that test harnesses and
    short-lived scripts can populate environment variables before any module
    accidentally triggers validation at import time.
    """
    return Settings()  # type: ignore[call-arg]
