"""System prompts and prompt templates.

Prompts live as `.txt` / `.jinja2` files in this package — never inline in
Python code.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_PROMPTS_DIR = Path(str(files("aiops_agent.prompts")))
_ENV = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    autoescape=select_autoescape(disabled_extensions=("txt", "jinja2")),
    keep_trailing_newline=True,
)


def load_prompt(name: str, **context: object) -> str:
    """Load a prompt by file name and optionally render Jinja variables.

    Args:
        name: File name within the prompts package (e.g. `"system.txt"`).
        **context: Variables for Jinja substitution.
    """
    template = _ENV.get_template(name)
    return template.render(**context)
