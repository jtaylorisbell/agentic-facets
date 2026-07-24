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
    model,
    *,
    uid_override: list[str] | None = None,
    recipe_filter: set[str] | None = None,
    concurrency: int = 4,
) -> list[RecipeSummary]:
    """Run every (recipe, question) pair and score it.

    Pairs run concurrently under a semaphore (``concurrency``) so a full sweep finishes in a few
    minutes instead of the sum of every sequential call. A pair that raises is recorded as an
    incorrect run rather than aborting the whole sweep.
    """
    scorer = answer_correctness_scorer()
    datasets: dict[str, OfficeQADataset] = {}
    discovered = _discover(recipe_filter)

    # Build the flat work list first (recipe, uid), preserving recipe order for the summary.
    summaries = {recipe: RecipeSummary(recipe=recipe) for recipe, _, _ in discovered}
    run_fns = {recipe: _load_run(app_path) for recipe, app_path, _ in discovered}
    work: list[tuple[str, str, str]] = []  # (recipe, subset, uid)
    for recipe, _, cfg in discovered:
        subset = cfg.get("subset", "pro")
        datasets.setdefault(subset, OfficeQADataset(subset))
        for uid in uid_override or cfg.get("uids", []):
            work.append((recipe, subset, uid))

    sem = asyncio.Semaphore(concurrency)
    done = 0
    total = len(work)

    async def _one(recipe: str, subset: str, uid: str) -> RecipeRun:
        nonlocal done
        dataset = datasets[subset]
        question = dataset.get(uid)
        async with sem:
            try:
                result = await run_fns[recipe](question, dataset, model=model)
                case = EvalCase(
                    id=uid, goal=question.question, metadata={"answer": question.answer}
                )
                score = scorer(case, result)
                run = RecipeRun(
                    recipe=recipe,
                    uid=uid,
                    correct=score.value,
                    model_calls=result.trace.model_calls,
                    total_tokens=result.trace.total_tokens,
                    steps=result.steps,
                    stopped_reason=result.stopped_reason,
                )
            except Exception as exc:  # noqa: BLE001 — one bad pair shouldn't sink the sweep
                run = RecipeRun(
                    recipe=recipe,
                    uid=uid,
                    correct=0.0,
                    model_calls=0,
                    total_tokens=0,
                    steps=0,
                    stopped_reason=f"error: {type(exc).__name__}",
                )
        done += 1
        print(f"  [{done}/{total}] {recipe} {uid} -> {run.correct:.0f}", flush=True)
        return run

    results = await asyncio.gather(*(_one(r, s, u) for r, s, u in work))
    for run in results:
        summaries[run.recipe].runs.append(run)
    return [summaries[recipe] for recipe, _, _ in discovered]


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


def _write_artifacts(summaries: list[RecipeSummary], out_dir: Path, model_name: str) -> None:
    """Write a machine-readable JSON and a human-readable Markdown table of the results.

    Committing these makes the cookbook's evidence reproducible: the numbers in the docs come
    from a file anyone can regenerate with ``uv run python evals/run_evals.py --out``.
    """
    import json
    from datetime import UTC, datetime

    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")

    payload = {
        "generated_at": generated_at,
        "model": model_name,
        "note": (
            "Real model + real data; answers scored by OfficeQA reward.py. Results vary run to "
            "run — the pattern (document access helps; extra agents are not automatically better) "
            "is the durable signal, not any single cell."
        ),
        "recipes": [
            {
                "recipe": s.recipe,
                "questions": s.n,
                "accuracy": round(s.accuracy, 4),
                "avg_model_calls": round(s.avg_model_calls, 2),
                "avg_tokens": round(s.avg_tokens, 1),
                "runs": [
                    {
                        "uid": r.uid,
                        "correct": r.correct,
                        "model_calls": r.model_calls,
                        "total_tokens": r.total_tokens,
                        "steps": r.steps,
                        "stopped_reason": r.stopped_reason,
                    }
                    for r in s.runs
                ],
            }
            for s in summaries
        ],
    }
    (out_dir / "latest.json").write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        "# Agentic FACETS — evaluation results",
        "",
        f"- Generated: `{generated_at}`",
        f"- Model: `{model_name}`",
        "- Questions per recipe / scoring: OfficeQA subset, graded by the official `reward.py`.",
        "",
        "Real model + real data, so numbers vary run to run. The **pattern** is the point:",
        "document access is the big lever; extra agents are not automatically better.",
        "",
        "| Recipe | Questions | Answer accuracy | Avg model calls | Avg tokens |",
        "|---|---|---|---|---|",
    ]
    for s in summaries:
        lines.append(
            f"| {s.recipe} | {s.n} | {s.accuracy:.2f} | "
            f"{s.avg_model_calls:.1f} | {s.avg_tokens:.0f} |"
        )
    lines += ["", "## Per-question detail", ""]
    for s in summaries:
        lines.append(f"### {s.recipe}")
        lines.append("")
        lines.append("| Question | Correct | Model calls | Tokens | Steps | Stopped |")
        lines.append("|---|---|---|---|---|---|")
        for r in s.runs:
            mark = "✓" if r.correct == 1.0 else "✗"
            lines.append(
                f"| {r.uid} | {mark} | {r.model_calls} | {r.total_tokens} | {r.steps} "
                f"| {r.stopped_reason} |"
            )
        lines.append("")
    (out_dir / "latest.md").write_text("\n".join(lines))
    print(f"\nWrote results to {out_dir / 'latest.json'} and {out_dir / 'latest.md'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the comparative FACETS evaluation.")
    parser.add_argument("--uids", help="Comma-separated question uids to override every eval.yaml.")
    parser.add_argument("--recipes", help="Comma-separated recipe dir names to limit the run.")
    parser.add_argument("--concurrency", type=int, default=4, help="Max concurrent runs.")
    parser.add_argument(
        "--out",
        nargs="?",
        const="evals/results",
        help="Write results to this dir (default evals/results) as latest.json + latest.md.",
    )
    ns = parser.parse_args()

    from facets.models import DatabricksModel

    model = DatabricksModel()
    uid_override = [u.strip() for u in ns.uids.split(",")] if ns.uids else None
    recipe_filter = {r.strip() for r in ns.recipes.split(",")} if ns.recipes else None

    summaries = asyncio.run(
        evaluate_all(
            model,
            uid_override=uid_override,
            recipe_filter=recipe_filter,
            concurrency=ns.concurrency,
        )
    )
    print()
    _print_table(summaries)
    if ns.out:
        _write_artifacts(summaries, _ROOT / ns.out, model.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
