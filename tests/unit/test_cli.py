"""CLI: argument wiring and version subcommand."""

from __future__ import annotations

from typer.testing import CliRunner

from aiops_agent import __version__
from aiops_agent.main import app

runner = CliRunner()


def test_version_subcommand_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_run_subcommand_invokes_agent(monkeypatch) -> None:
    captured: dict[str, str] = {}

    from aiops_agent.agent import AgentResult

    class _FakeAgent:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def run(self, task: str) -> AgentResult:
            captured["task"] = task
            return AgentResult(
                final_text="resolved", iterations=1, stop_reason="end_turn"
            )

    monkeypatch.setattr("aiops_agent.main.Agent", _FakeAgent)

    result = runner.invoke(app, ["run", "investigate latency"])
    assert result.exit_code == 0
    assert "resolved" in result.stdout
    assert captured["task"] == "investigate latency"
