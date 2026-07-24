"""Scorers for the eval harness.

Re-exports the built-in scorers from :mod:`facets.evaluation` so eval configs and the runner
have a single import site, and so custom scenario-specific scorers can be added here later
without touching the core package.
"""

from __future__ import annotations

from facets.evaluation import (
    Score,
    Scorer,
    task_success_scorer,
    tool_correctness_scorer,
)

__all__ = ["Score", "Scorer", "task_success_scorer", "tool_correctness_scorer"]


def default_scorers() -> list[Scorer]:
    """The scorer set used by the comparative eval."""
    return [task_success_scorer(), tool_correctness_scorer()]
