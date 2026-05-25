"""CLI entry point.

Run via:

    python -m aiops_agent.main run "Investigate the latency spike on api-1"

Or, after installation:

    aiops-agent run "Investigate the latency spike on api-1"
"""

from __future__ import annotations

import typer

from aiops_agent.agent import Agent
from aiops_agent.config import get_settings
from aiops_agent.utils.logging import configure_logging, get_logger

app = typer.Typer(
    name="aiops-agent",
    help="AI-powered IT Operations agent.",
    no_args_is_help=True,
)


@app.command()
def run(
    task: str = typer.Argument(..., help="Natural-language task description."),
    json_logs: bool = typer.Option(
        False, "--json-logs", help="Emit logs as JSON (production)."
    ),
) -> None:
    """Run the agent against a single task and print its final response."""
    settings = get_settings()
    configure_logging(settings.log_level, json_output=json_logs)
    logger = get_logger(__name__)

    logger.info("agent.start", task=task)
    result = Agent(settings=settings).run(task)
    logger.info(
        "agent.done",
        iterations=result.iterations,
        stop_reason=result.stop_reason,
    )
    typer.echo(result.final_text)


@app.command()
def version() -> None:
    """Print the installed package version."""
    from aiops_agent import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
