"""Shared helpers for the recipe apps.

Kept deliberately small: model selection (offline FakeModel vs. live Databricks) and a couple
of console helpers. Recipe-specific logic — including each recipe's scripted FakeModel plan —
lives in that recipe's own ``app.py`` so it can be read top-to-bottom in isolation.

Import this from a recipe only after the recipe's ``app.py`` has put the repo root on the path.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from facets.agents import AgentResult
    from facets.models import ModelProvider


def parse_recipe_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use a live Databricks foundation-model endpoint instead of the offline FakeModel.",
    )
    parser.add_argument(
        "--pipeline",
        default=None,
        help="Pipeline to investigate (defaults to the canonical incident).",
    )
    return parser.parse_args()


def live_model() -> ModelProvider:
    """Build a Databricks-backed model from the environment (DATABRICKS_HOST/TOKEN/FACETS_MODEL)."""
    from facets.models import DatabricksModel

    return DatabricksModel()


def print_result(title: str, result: AgentResult) -> None:
    """Pretty-print a recipe result and its trace summary."""
    from rich.console import Console

    console = Console()
    console.rule(f"[bold]{title}")
    # markup=False: recipe answers are free text and may contain "[...]" (e.g. a router prefix);
    # don't let Rich interpret those as style tags.
    console.print(result.answer, markup=False)
    console.rule("[dim]Trace")
    summary = result.trace.summary()
    summary["stopped_reason"] = result.stopped_reason
    summary["steps"] = result.steps
    console.print(summary)
