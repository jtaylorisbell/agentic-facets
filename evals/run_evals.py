"""Comparative evaluation: the same incident, every architecture, side by side.

This is the cookbook's evidence artifact — the "we built the same agent several ways; here's
what changed" table. For each recipe it:

  1. loads the recipe's ``eval.yaml`` (goal + ground truth),
  2. runs the recipe's ``run()`` entrypoint with the offline scripted FakeModel,
  3. scores the result (task success, tool-use correctness), and
  4. records cost metrics (model calls, tokens, latency, steps).

It then prints one row per recipe so the tradeoffs are visible at a glance. Because the offline
runs are deterministic, this doubles as a regression test (see ``tests/`` which import ``main``).

    uv run python evals/run_evals.py
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.evaluation import EvalCase, Evaluator, RunReport  # noqa: E402
from facets.models import ModelProvider  # noqa: E402

RECIPES_DIR = _ROOT / "recipes"


@dataclass
class RecipeEval:
    recipe: str
    case: EvalCase
    run_fn: callable


def _discover() -> list[RecipeEval]:
    """Find every recipe that ships an eval.yaml, in recipe-number order."""
    found: list[RecipeEval] = []
    for recipe_dir in sorted(RECIPES_DIR.iterdir()):
        eval_path = recipe_dir / "eval.yaml"
        app_path = recipe_dir / "app.py"
        if not (eval_path.exists() and app_path.exists()):
            continue
        cfg = yaml.safe_load(eval_path.read_text())
        c = cfg["case"]
        case = EvalCase(
            id=c["id"],
            goal=c["goal"],
            expected_root_cause=c.get("expected_root_cause"),
            expected_tools=c.get("expected_tools", []),
            metadata={"pipeline": c.get("pipeline")},
        )
        run_fn = _load_run(app_path)
        found.append(RecipeEval(recipe=recipe_dir.name, case=case, run_fn=run_fn))
    return found


def _load_run(app_path: Path):
    spec = importlib.util.spec_from_file_location(f"eval_{app_path.parent.name}", app_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run


async def evaluate_all(model: ModelProvider | None = None) -> list[RunReport]:
    """Run and score every discovered recipe. ``model=None`` uses each recipe's scripted model."""
    evaluator = Evaluator()
    reports: list[RunReport] = []
    for item in _discover():
        pipeline = item.case.metadata.get("pipeline")
        kwargs = {"model": model} if model is not None else {}
        result = await item.run_fn(pipeline, **kwargs) if pipeline else await item.run_fn(**kwargs)
        reports.append(evaluator.evaluate(item.case, item.recipe, result))
    return reports


def _print_table(reports: list[RunReport]) -> None:
    from rich.console import Console
    from rich.table import Table

    table = Table(title="Agentic FACETS — same incident, compared across architectures")
    table.add_column("Recipe", style="bold")
    table.add_column("Task\nsuccess", justify="right")
    table.add_column("Tool\ncorrectness", justify="right")
    table.add_column("Model\ncalls", justify="right")
    table.add_column("Total\ntokens", justify="right")
    table.add_column("Steps", justify="right")
    table.add_column("Stopped", justify="left")

    for r in reports:
        table.add_row(
            r.recipe,
            f"{r.score('task_success'):.2f}",
            f"{r.score('tool_correctness'):.2f}",
            str(r.model_calls),
            str(r.total_tokens),
            str(r.steps),
            r.stopped_reason,
        )

    Console().print(table)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the comparative FACETS evaluation.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Drive every recipe with a live Databricks endpoint instead of scripted models.",
    )
    ns = parser.parse_args()

    model = None
    if ns.live:
        from facets.models import DatabricksModel

        model = DatabricksModel()

    reports = asyncio.run(evaluate_all(model))
    _print_table(reports)

    # Non-zero exit if any recipe failed its task — makes this usable as a CI gate.
    failed = [r.recipe for r in reports if r.score("task_success") < 1.0]
    if failed:
        print(f"\nFAILED task success: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
