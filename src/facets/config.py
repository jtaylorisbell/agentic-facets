"""Environment/config loading.

Agentic FACETS runs against real services — a Databricks model and the gated OfficeQA dataset —
so it needs credentials. Those live in a gitignored ``.env`` at the repo root. This module loads
that file into ``os.environ`` (without overwriting anything already set) and gives callers a
single, friendly place to read required settings with actionable error messages.

We parse ``.env`` ourselves rather than take a python-dotenv dependency: the format we need is
trivial (``KEY=value`` lines, ``#`` comments), and one less dependency keeps the runtime lean.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _find_dotenv() -> Path | None:
    """Walk up from this file to find a ``.env`` at the repo root."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=1)
def load_env() -> None:
    """Load ``.env`` into ``os.environ`` once. Existing environment values win.

    Idempotent and cached, so importing it from many places is free. If there is no ``.env``
    (for example in CI where secrets are injected directly), this is a no-op.
    """
    path = _find_dotenv()
    if path is None:
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Do not clobber a value the process already has (real env beats the file).
        os.environ.setdefault(key, value)


class MissingCredential(RuntimeError):
    """Raised when a required credential is absent, with instructions on how to set it."""


def require_env(key: str, *, why: str, how: str) -> str:
    """Return ``os.environ[key]`` or raise a :class:`MissingCredential` that explains the fix."""
    load_env()
    value = os.environ.get(key)
    if not value:
        raise MissingCredential(
            f"{key} is not set. {why}\n"
            f"How to fix: {how}\n"
            f"Tip: copy .env.example to .env and fill in the values."
        )
    return value
