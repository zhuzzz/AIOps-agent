# AIOps-agent

AI-powered IT Operations (AIOps) agent for automated infrastructure monitoring,
incident detection, root cause analysis, and remediation workflows.

See [CLAUDE.md](./CLAUDE.md) for the full architecture, conventions, and
development guide.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # then fill in ANTHROPIC_API_KEY

docker-compose up -d   # optional local deps (redis, postgres)
aiops-agent run
```

## Layout

```
src/aiops_agent/
├── main.py          # Typer CLI entry point
├── agent.py         # Core observe → think → act loop
├── config.py        # pydantic-settings, env-driven
├── llm/             # Anthropic client wrapper (single chokepoint)
├── tools/           # Capabilities exposed to the LLM
├── integrations/    # Third-party (PagerDuty, Datadog, ...)
├── models/          # Pydantic schemas
├── prompts/         # System prompts as .txt / .jinja2
└── utils/           # Shared helpers
```

## Development

```bash
ruff format . && ruff check . --fix
mypy src/
pytest tests/unit/ --cov=aiops_agent
```
