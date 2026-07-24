"""Scorers for the eval harness.

Single import site for the scorers the comparative eval uses. The headline scorer for the
OfficeQA scenario is :func:`~facets.officeqa.answer_correctness_scorer`, which wraps the official
``reward.py``; the generic scorers from :mod:`facets.evaluation` remain available for custom use.
"""

from __future__ import annotations

from facets.evaluation import Score, Scorer, task_success_scorer, tool_correctness_scorer
from facets.officeqa import answer_correctness_scorer

__all__ = [
    "Score",
    "Scorer",
    "answer_correctness_scorer",
    "task_success_scorer",
    "tool_correctness_scorer",
]


def default_scorers() -> list[Scorer]:
    """The scorer set used by the comparative eval (OfficeQA answer correctness)."""
    return [answer_correctness_scorer()]
