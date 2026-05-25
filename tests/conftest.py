"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure tests never hit a real API by default."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
    monkeypatch.setenv("AIOPS_LOG_LEVEL", "DEBUG")
    # Drop the cached settings singleton so each test sees its own env.
    from aiops_agent.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def env_with(monkeypatch: pytest.MonkeyPatch):
    """Convenience: set additional env vars within a test."""

    def _set(**kwargs: str) -> None:
        for key, value in kwargs.items():
            monkeypatch.setenv(key, value)
        from aiops_agent.config import get_settings

        get_settings.cache_clear()

    return _set


# Re-export so unused-import warnings stay quiet.
_ = os
