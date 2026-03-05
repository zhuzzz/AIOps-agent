# CLAUDE.md — AIOps Agent

This file provides guidance for AI assistants (Claude and others) working in
this repository. Read it before making any changes.

---

## Project Overview

**AIOps-agent** is an AI-powered IT Operations (AIOps) agent designed to
automate and assist with infrastructure monitoring, incident detection, root
cause analysis, and remediation workflows. The agent ingests telemetry data
(metrics, logs, traces) and uses AI models to surface actionable insights.

> **Status:** This repository is newly initialized. The sections below define
> the intended architecture and conventions to follow as the project is built.

---

## Repository Structure (Intended)

```
AIOps-agent/
├── CLAUDE.md               # This file
├── README.md               # Human-facing documentation
├── .env.example            # Environment variable template (never commit .env)
├── .gitignore
├── pyproject.toml          # Project metadata & dependencies (or requirements.txt)
├── docker-compose.yml      # Local dev environment
│
├── src/
│   └── aiops_agent/
│       ├── __init__.py
│       ├── main.py         # Entry point / CLI
│       ├── agent.py        # Core agent loop
│       ├── config.py       # Configuration management
│       ├── models/         # Data models / schemas
│       ├── tools/          # Agent tools (bash exec, API calls, etc.)
│       ├── integrations/   # Third-party integrations (PagerDuty, Datadog, etc.)
│       ├── llm/            # LLM client wrappers
│       └── utils/          # Shared utilities
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
│
├── scripts/                # One-off maintenance / deployment scripts
└── docs/                   # Architecture diagrams, runbooks
```

---

## Development Environment

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for local dependencies)
- An Anthropic API key (set `ANTHROPIC_API_KEY` in `.env`)

### Setup

```bash
# Clone and enter the repo
git clone <repo-url>
cd AIOps-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install in editable mode with dev extras
pip install -e ".[dev]"

# Copy environment template and fill in values
cp .env.example .env
```

### Running the Agent

```bash
# Start local dependencies (if any)
docker-compose up -d

# Run the agent
python -m aiops_agent.main

# Or via the installed CLI entry point
aiops-agent run
```

---

## Development Workflows

### Adding a New Tool

1. Create a new module under `src/aiops_agent/tools/<tool_name>.py`.
2. Define the tool as a function with a clear docstring — this becomes the
   tool description passed to the LLM.
3. Register it in `src/aiops_agent/tools/__init__.py`.
4. Write unit tests in `tests/unit/tools/test_<tool_name>.py`.

### Adding a New Integration

1. Create `src/aiops_agent/integrations/<service>.py`.
2. Use an async-first design (`async def`) for all I/O operations.
3. Store credentials in environment variables; never hard-code them.
4. Add an integration test in `tests/integration/` gated by a feature flag or
   `pytest.mark.integration`.

### Modifying the Agent Loop

The core reasoning loop lives in `src/aiops_agent/agent.py`. Changes there
affect the fundamental behavior of the agent; proceed carefully and write tests
for any logic changes.

---

## Testing

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=aiops_agent --cov-report=term-missing

# Run integration tests (requires live credentials in .env)
pytest tests/integration/ -v -m integration

# Run all tests
pytest
```

### Test Conventions

- Use `pytest` with `pytest-asyncio` for async tests.
- Mock all external HTTP calls with `respx` or `unittest.mock`.
- Integration tests must be marked `@pytest.mark.integration` and must pass
  without modifying production systems.
- Aim for >80% unit test coverage on new code.

---

## Code Conventions

### Style

- **Formatter:** `ruff format` (Black-compatible, line length 88).
- **Linter:** `ruff check` — no warnings allowed in CI.
- **Type checking:** `mypy --strict` on the `src/` directory.
- All public functions and classes require type annotations.
- Docstrings use the Google style.

```bash
# Format & lint
ruff format .
ruff check . --fix

# Type check
mypy src/
```

### Naming

| Entity | Convention | Example |
|---|---|---|
| Files/modules | `snake_case` | `root_cause.py` |
| Classes | `PascalCase` | `IncidentDetector` |
| Functions/variables | `snake_case` | `detect_anomaly()` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_TIMEOUT` |
| Environment vars | `UPPER_SNAKE_CASE` | `ANTHROPIC_API_KEY` |

### Commits

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

[optional body]
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`.

Examples:
```
feat(tools): add bash execution tool with timeout support
fix(agent): handle empty tool call response from LLM
docs: update CLAUDE.md with integration test instructions
```

---

## LLM / AI Conventions

This project uses the **Anthropic Claude API**. All LLM calls must go through
the wrapper in `src/aiops_agent/llm/`.

### Key Rules

1. **Never hard-code model names** in tool code — always use the constant
   from `config.py` (e.g., `settings.llm_model`).
2. **Default model:** `claude-sonnet-4-6` for production; use
   `claude-haiku-4-5-20251001` for lightweight/fast paths.
3. **System prompts** live in `src/aiops_agent/prompts/` as `.txt` or `.jinja2`
   files — not inline in Python code.
4. **Tool schemas** are defined as Python dataclasses with `pydantic` and
   converted to JSON Schema automatically — never write raw JSON schemas by
   hand.
5. Log all LLM requests and responses at `DEBUG` level. Do not log sensitive
   data (secrets, PII).
6. Set explicit `max_tokens` on every API call — never rely on the default.

### Rate Limits & Retries

Use the built-in retry logic in the LLM wrapper. Do not implement ad-hoc retry
loops elsewhere. Back off exponentially on `429` and `529` responses.

---

## Configuration

All configuration is loaded via `src/aiops_agent/config.py` using `pydantic-settings`.
Values are read from environment variables (and `.env` in development).

```python
# Example — never access os.environ directly in application code
from aiops_agent.config import settings

api_key = settings.anthropic_api_key
```

Required environment variables are documented in `.env.example`. Adding a new
setting requires:
1. A field in the `Settings` class in `config.py`.
2. A corresponding entry in `.env.example` with a comment.

---

## Security

- **Never commit secrets** (API keys, passwords, tokens). Use `.env` (gitignored).
- **Never execute unsanitized user input** in shell commands. Always use
  argument lists, not shell strings.
- **Validate all external data** at ingestion boundaries using Pydantic models.
- Dependency updates: run `pip-audit` before merging changes to
  `pyproject.toml`.

---

## CI/CD

CI runs on every pull request and enforces:

1. `ruff format --check` — formatting
2. `ruff check` — linting
3. `mypy src/` — type checking
4. `pytest tests/unit/` — unit tests with coverage gate (≥80%)

Merges to `main` additionally run integration tests in a sandboxed environment.

---

## Branching Strategy

| Branch | Purpose |
|---|---|
| `main` | Stable, production-ready |
| `develop` | Integration branch for features |
| `feat/<name>` | Feature development |
| `fix/<name>` | Bug fixes |
| `claude/<id>` | AI-assistant development branches |

PRs require at least one human review before merging to `main`.

---

## Glossary

| Term | Definition |
|---|---|
| AIOps | AI for IT Operations — using ML/AI to automate ops tasks |
| Agent loop | The reasoning cycle: observe → think → act → observe |
| Tool | A callable capability exposed to the LLM (bash, API call, etc.) |
| Telemetry | Metrics, logs, and traces from infrastructure |
| RCA | Root Cause Analysis |
| Runbook | A documented procedure for handling a specific incident type |

---

*Last updated: 2026-03-05. Keep this file current as the project evolves.*
