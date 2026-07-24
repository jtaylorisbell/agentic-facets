"""Comparative evaluation: the same questions, every architecture, side by side.

This is the cookbook's evidence artifact — the "we built the same agent several ways; here's what
changed" table. For each recipe it:

  1. loads the recipe's ``eval.yaml`` (a list of OfficeQA question uids),
  2. runs the recipe's ``run(question, dataset, model=...)`` entrypoint on each question with a
     real Databricks model,
  3. scores each answer with the official OfficeQA ``reward.py`` (via answer_correctness_scorer),
  4. records cost metrics (model calls, tokens, steps).

It then prints one row per recipe: mean answer correctness and mean cost over the question set.
Unlike the old scenario, these runs hit a real model and real data — so results vary run to run,
and a wrong answer is a real wrong answer.

    uv run python evals/run_evals.py                 # every recipe, its eval.yaml questions
    uv run python evals/run_evals.py --uids UID0121  # override the question set
    uv run python evals/run_evals.py --recipes 00_closed_book_baseline,01_single_tool_agent
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.evaluation import EvalCase  # noqa: E402
from facets.officeqa import OfficeQADataset, answer_correctness_scorer  # noqa: E402

RECIPES_DIR = _ROOT / "recipes"


@dataclass
class RecipeRun:
    recipe: str
    uid: str
    correct: float
    model_calls: int
    total_tokens: int
    steps: int
    stopped_reason: str


@dataclass
class RecipeSummary:
    recipe: str
    runs: list[RecipeRun] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.runs)

    @property
    def accuracy(self) -> float:
        return sum(r.correct for r in self.runs) / self.n if self.n else 0.0

    @property
    def avg_model_calls(self) -> float:
        return sum(r.model_calls for r in self.runs) / self.n if self.n else 0.0

    @property
    def avg_tokens(self) -> float:
        return sum(r.total_tokens for r in self.runs) / self.n if self.n else 0.0


def _load_run(app_path: Path):
    name = f"eval_{app_path.parent.name}"
    spec = importlib.util.spec_from_file_location(name, app_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # register before exec (dataclass modules need this)
    spec.loader.exec_module(module)
    return module.run


def _discover(recipe_filter: set[str] | None) -> list[tuple[str, Path, dict]]:
    """Return (recipe_name, app_path, eval_cfg) for each runnable recipe, in number order."""
    found = []
    for recipe_dir in sorted(RECIPES_DIR.iterdir()):
        if not (recipe_dir / "app.py").exists() or not (recipe_dir / "eval.yaml").exists():
            continue
        if recipe_filter and recipe_dir.name not in recipe_filter:
            continue
        cfg = yaml.safe_load((recipe_dir / "eval.yaml").read_text())
        found.append((recipe_dir.name, recipe_dir / "app.py", cfg))
    return found


async def evaluate_all(
    model, *, uid_override: list[str] | None = None, recipe_filter: set[str] | None = None
) -> list[RecipeSummary]:
    scorer = answer_correctness_scorer()
    datasets: dict[str, OfficeQADataset] = {}
    summaries: list[RecipeSummary] = []

    for recipe, app_path, cfg in _discover(recipe_filter):
        run_fn = _load_run(app_path)
        subset = cfg.get("subset", "pro")
        dataset = datasets.setdefault(subset, OfficeQADataset(subset))
        uids = uid_override or cfg.get("uids", [])
        summary = RecipeSummary(recipe=recipe)

        for uid in uids:
            question = dataset.get(uid)
            print(f"  [{recipe}] {uid} …", flush=True)
            result = await run_fn(question, dataset, model=model)
            case = EvalCase(id=uid, goal=question.question, metadata={"answer": question.answer})
            score = scorer(case, result)
            summary.runs.append(
                RecipeRun(
                    recipe=recipe,
                    uid=uid,
                    correct=score.value,
                    model_calls=result.trace.model_calls,
                    total_tokens=result.trace.total_tokens,
                    steps=result.steps,
                    stopped_reason=result.stopped_reason,
                )
            )
        summaries.append(summary)
    return summaries


def _print_table(summaries: list[RecipeSummary]) -> None:
    from rich.console import Console
    from rich.table import Table

    table = Table(title="Agentic FACETS — same OfficeQA questions, compared across architectures")
    table.add_column("Recipe", style="bold")
    table.add_column("Questions", justify="right")
    table.add_column("Answer\naccuracy", justify="right")
    table.add_column("Avg model\ncalls", justify="right")
    table.add_column("Avg\ntokens", justify="right")

    for s in summaries:
        table.add_row(
            s.recipe,
            str(s.n),
            f"{s.accuracy:.2f}",
            f"{s.avg_model_calls:.1f}",
            f"{s.avg_tokens:.0f}",
        )
    Console().print(table)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the comparative FACETS evaluation.")
    parser.add_argument("--uids", help="Comma-separated question uids to override every eval.yaml.")
    parser.add_argument("--recipes", help="Comma-separated recipe dir names to limit the run.")
    ns = parser.parse_args()

    from facets.models import DatabricksModel

    model = DatabricksModel()
    uid_override = [u.strip() for u in ns.uids.split(",")] if ns.uids else None
    recipe_filter = {r.strip() for r in ns.recipes.split(",")} if ns.recipes else None

    summaries = asyncio.run(
        evaluate_all(model, uid_override=uid_override, recipe_filter=recipe_filter)
    )
    print()
    _print_table(summaries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
