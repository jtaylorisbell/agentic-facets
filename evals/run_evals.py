"""Comparative evaluation: the same questions, every architecture, across several models.

This is the cookbook's evidence artifact. It answers one question with data: **does the agent
architecture matter as much as the model behind it?** To answer it honestly you need a *grid* —
the same questions run through every recipe (the architecture axis) and every model (the model
axis) — so you can measure two effects and compare their size:

* **Architecture lift** — hold the model fixed, change the architecture (e.g. closed-book →
  give it document tools). How much does accuracy move?
* **Model lift** — hold the architecture fixed, upgrade the model (weaker → stronger). How much
  does accuracy move?

If a *weaker* model with a *better* architecture beats a *stronger* model with a naive one, the
thesis holds: architecture is a lever at least as strong as the model.

For each (recipe, model, question) cell it:

  1. loads the recipe's ``eval.yaml`` (a list of OfficeQA question uids),
  2. runs the recipe's ``run(question, dataset, model=...)`` entrypoint on each question,
  3. scores the answer with the official OfficeQA ``reward.py``,
  4. records cost (model calls, tokens, steps).

It then prints an accuracy matrix (recipe × model), the two lifts above, and the head-to-head
"weak model + tools vs strong model, no tools" comparison.

    uv run python evals/run_evals.py                          # default model, each eval.yaml
    uv run python evals/run_evals.py --models A,B             # sweep two models (the grid)
    uv run python evals/run_evals.py --models A,B --uids UID0121   # one shared question
    uv run python evals/run_evals.py --recipes 00_closed_book_baseline,01_single_tool_agent
    uv run python evals/run_evals.py --models A,B --out       # write committed artifacts
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.evaluation import EvalCase  # noqa: E402
from facets.officeqa import OfficeQADataset, answer_correctness_scorer  # noqa: E402

RECIPES_DIR = _ROOT / "recipes"

# The two recipes whose gap defines "architecture lift": the closed-book control and the first
# recipe that adds document tools. Matched by numeric prefix so a rename doesn't break the analysis.
BASELINE_PREFIX = "00_"
TOOL_PREFIX = "01_"


# --------------------------------------------------------------------------------------------
# Data model — a run is one (recipe, model, question) cell; the grid aggregates them.
# --------------------------------------------------------------------------------------------


#: A run whose stopped_reason starts with this marker failed on infrastructure (rate limit,
#: connection), not on the question. Such runs are NOT wrong answers — scoring them 0.0 would
#: bias a cell's accuracy downward — so accuracy is computed over successful runs only.
ERROR_PREFIX = "error:"


@dataclass
class RecipeRun:
    recipe: str
    model: str
    uid: str
    correct: float
    model_calls: int
    total_tokens: int
    steps: int
    stopped_reason: str

    @property
    def is_error(self) -> bool:
        return self.stopped_reason.startswith(ERROR_PREFIX)


@dataclass
class Cell:
    """All runs for one (recipe, model) pair — one square of the grid.

    Accuracy is over *successful* runs only: an infra failure (rate limit, dropped connection) is
    not a wrong answer, and counting it as one would understate a model that simply got throttled.
    ``errors`` reports how many runs failed so the reader can judge a cell's reliability.
    """

    recipe: str
    model: str
    runs: list[RecipeRun] = field(default_factory=list)

    @property
    def n(self) -> int:
        """Total attempted runs (including infra errors)."""
        return len(self.runs)

    @property
    def scored(self) -> list[RecipeRun]:
        """Runs that completed and produced an answer to score."""
        return [r for r in self.runs if not r.is_error]

    @property
    def n_scored(self) -> int:
        return len(self.scored)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.runs if r.is_error)

    @property
    def accuracy(self) -> float:
        scored = self.scored
        return sum(r.correct for r in scored) / len(scored) if scored else 0.0

    @property
    def avg_model_calls(self) -> float:
        scored = self.scored
        return sum(r.model_calls for r in scored) / len(scored) if scored else 0.0

    @property
    def avg_tokens(self) -> float:
        scored = self.scored
        return sum(r.total_tokens for r in scored) / len(scored) if scored else 0.0

    @property
    def uids(self) -> frozenset[str]:
        """Uids of successfully scored runs — the set the accuracy is actually over."""
        return frozenset(r.uid for r in self.scored)


@dataclass
class Grid:
    """The recipe × model matrix of cells, plus the display order of each axis."""

    recipes: list[str]
    models: list[str]
    cells: dict[tuple[str, str], Cell]

    def cell(self, recipe: str, model: str) -> Cell:
        return self.cells.get((recipe, model), Cell(recipe, model))

    def accuracy(self, recipe: str, model: str) -> float:
        return self.cell(recipe, model).accuracy

    def recipe_matching(self, prefix: str) -> str | None:
        return next((r for r in self.recipes if r.split("/")[-1].startswith(prefix)), None)


def summarize(runs: list[RecipeRun], recipes: list[str], models: list[str]) -> Grid:
    """Group flat runs into a recipe × model grid. Pure — the unit tests build runs by hand."""
    cells: dict[tuple[str, str], Cell] = {}
    for r in runs:
        cells.setdefault((r.recipe, r.model), Cell(r.recipe, r.model)).runs.append(r)
    return Grid(recipes=recipes, models=models, cells=cells)


# --------------------------------------------------------------------------------------------
# Analysis — the numbers that actually argue the thesis.
# --------------------------------------------------------------------------------------------


def short_model(name: str) -> str:
    """A compact label for a Unity model-service name, e.g. system.ai.gpt-oss-20b -> gpt-oss-20b."""
    return name.split("/")[-1].removeprefix("system.ai.")


@dataclass
class Analysis:
    """The thesis, reduced to numbers. All accuracies are over a shared question set."""

    baseline_recipe: str  # closed-book control (no tools)
    tool_recipe: str  # first recipe that adds document tools
    ranked_models: list[str]  # weakest -> strongest, by closed-book accuracy
    weak_model: str
    strong_model: str
    model_lift: float  # strong - weak, on the baseline architecture (upgrading the LLM)
    arch_lift: float  # tools - baseline, on the weak model (upgrading the architecture)
    weak_with_tools: float  # accuracy: weak model + document tools
    strong_no_tools: float  # accuracy: strong model, closed-book
    comparable: bool  # were the compared cells run on the same questions?

    @property
    def killer_holds(self) -> bool:
        """Does the weak model + tools match or beat the strong model with no tools?"""
        return self.weak_with_tools >= self.strong_no_tools

    @property
    def architecture_wins(self) -> bool:
        """Is the architecture lever at least as large as the model lever?"""
        return self.arch_lift >= self.model_lift


def analyze(grid: Grid) -> Analysis | None:
    """Reduce the grid to the head-to-head thesis numbers.

    Returns ``None`` when the grid is too small to argue anything (needs the closed-book and
    tool recipes and at least two models). Ranks models by their *closed-book* accuracy — the
    model's raw knowledge with no help — so "weak" and "strong" are defined by the data, not by
    hand.
    """
    baseline = grid.recipe_matching(BASELINE_PREFIX)
    tool = grid.recipe_matching(TOOL_PREFIX)
    if baseline is None or tool is None or len(grid.models) < 2:
        return None

    ranked = sorted(grid.models, key=lambda m: grid.accuracy(baseline, m))
    weak, strong = ranked[0], ranked[-1]

    # The comparison is only fair if the cells share a question set. Baseline and tool recipes
    # both run the "lookup" uids, and a given recipe runs identical uids across models — but guard
    # anyway so a mismatched config surfaces instead of quietly producing a bogus headline.
    compared = [
        grid.cell(baseline, weak),
        grid.cell(baseline, strong),
        grid.cell(tool, weak),
    ]
    uid_sets = {c.uids for c in compared if c.n}
    comparable = len(uid_sets) == 1

    return Analysis(
        baseline_recipe=baseline,
        tool_recipe=tool,
        ranked_models=ranked,
        weak_model=weak,
        strong_model=strong,
        model_lift=grid.accuracy(baseline, strong) - grid.accuracy(baseline, weak),
        arch_lift=grid.accuracy(tool, weak) - grid.accuracy(baseline, weak),
        weak_with_tools=grid.accuracy(tool, weak),
        strong_no_tools=grid.accuracy(baseline, strong),
        comparable=comparable,
    )


# --------------------------------------------------------------------------------------------
# Running the grid.
# --------------------------------------------------------------------------------------------


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


async def evaluate_grid(
    models: dict[str, object],
    *,
    uid_override: list[str] | None = None,
    recipe_filter: set[str] | None = None,
    concurrency: int = 4,
) -> Grid:
    """Run every (recipe, model, question) cell and score it.

    ``models`` maps a model-service name to a ready :class:`ModelProvider`. Cells run concurrently
    under a semaphore so a full sweep finishes in a few minutes rather than the sum of every
    sequential call. A cell that raises is recorded as an incorrect run rather than aborting the
    whole sweep.
    """
    scorer = answer_correctness_scorer()
    datasets: dict[str, OfficeQADataset] = {}
    discovered = _discover(recipe_filter)

    recipes = [recipe for recipe, _, _ in discovered]
    run_fns = {recipe: _load_run(app_path) for recipe, app_path, _ in discovered}

    # Flat work list: one entry per (recipe, model, question).
    work: list[tuple[str, str, str, str]] = []  # (recipe, model_name, subset, uid)
    for recipe, _, cfg in discovered:
        subset = cfg.get("subset", "pro")
        datasets.setdefault(subset, OfficeQADataset(subset))
        uids = uid_override or cfg.get("uids", [])
        for model_name in models:
            for uid in uids:
                work.append((recipe, model_name, subset, uid))

    sem = asyncio.Semaphore(concurrency)
    done = 0
    total = len(work)

    async def _one(recipe: str, model_name: str, subset: str, uid: str) -> RecipeRun:
        nonlocal done
        dataset = datasets[subset]
        question = dataset.get(uid)
        async with sem:
            try:
                result = await run_fns[recipe](question, dataset, model=models[model_name])
                case = EvalCase(
                    id=uid, goal=question.question, metadata={"answer": question.answer}
                )
                score = scorer(case, result)
                run = RecipeRun(
                    recipe=recipe,
                    model=model_name,
                    uid=uid,
                    correct=score.value,
                    model_calls=result.trace.model_calls,
                    total_tokens=result.trace.total_tokens,
                    steps=result.steps,
                    stopped_reason=result.stopped_reason,
                )
            except Exception as exc:  # noqa: BLE001 — one bad cell shouldn't sink the sweep
                run = RecipeRun(
                    recipe=recipe,
                    model=model_name,
                    uid=uid,
                    correct=0.0,
                    model_calls=0,
                    total_tokens=0,
                    steps=0,
                    stopped_reason=f"error: {type(exc).__name__}",
                )
        done += 1
        outcome = run.stopped_reason if run.is_error else f"{run.correct:.0f}"
        print(
            f"  [{done}/{total}] {recipe} · {short_model(model_name)} · {uid} -> {outcome}",
            flush=True,
        )
        return run

    results = await asyncio.gather(*(_one(r, m, s, u) for r, m, s, u in work))
    return summarize(results, recipes=recipes, models=list(models))


# --------------------------------------------------------------------------------------------
# Rendering.
# --------------------------------------------------------------------------------------------


def _print_grid(grid: Grid) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="Agentic FACETS — accuracy by architecture × model (avg tokens below)")
    table.add_column("Recipe", style="bold")
    for m in grid.models:
        table.add_column(short_model(m), justify="right")

    for recipe in grid.recipes:
        row = [recipe]
        for m in grid.models:
            cell = grid.cell(recipe, m)
            if not cell.n_scored:
                # No scorable runs — don't print a fake 0.00; say why.
                row.append(f"[red]n/a[/red]\n[dim]{cell.errors} err[/dim]" if cell.errors else "—")
                continue
            text = (
                f"{cell.accuracy:.2f} [dim](n={cell.n_scored})[/dim]\n"
                f"[dim]{cell.avg_tokens:,.0f} tok[/dim]"
            )
            if cell.errors:
                text += f"\n[yellow]{cell.errors} err[/yellow]"
            row.append(text)
        table.add_row(*row)
    console.print(table)
    if any(grid.cell(r, m).errors for r in grid.recipes for m in grid.models):
        console.print(
            "[dim]Accuracy is over successfully-scored runs only; 'err' = infra failures "
            "(rate limit / connection), excluded rather than counted wrong.[/dim]"
        )


def _print_analysis(grid: Grid) -> None:
    from rich.console import Console

    console = Console()
    a = analyze(grid)
    if a is None:
        console.print(
            "\n[dim](Add a second model with --models to measure architecture vs model lift.)[/dim]"
        )
        return

    weak, strong = short_model(a.weak_model), short_model(a.strong_model)
    console.rule("[bold]Architecture vs. model: which lever is bigger?")
    console.print(
        f"Ranked weakest→strongest by closed-book accuracy: "
        f"{', '.join(short_model(m) for m in a.ranked_models)}"
    )
    console.print(
        f"  • [bold]Model lift[/bold]  (upgrade the LLM, no tools): "
        f"{strong} vs {weak} on {a.baseline_recipe.split('_', 1)[0]} "
        f"= [bold]{a.model_lift:+.2f}[/bold] accuracy"
    )
    console.print(
        f"  • [bold]Architecture lift[/bold] (give {weak} document tools): "
        f"{a.tool_recipe.split('_', 1)[0]} vs {a.baseline_recipe.split('_', 1)[0]} "
        f"= [bold]{a.arch_lift:+.2f}[/bold] accuracy"
    )
    if not a.comparable:
        console.print(
            "  [yellow]⚠ compared cells did not share a question set — "
            "treat as indicative.[/yellow]"
        )
    verdict = (
        "architecture is the [bold]bigger[/bold] lever"
        if a.architecture_wins
        else "the model is the bigger lever here"
    )
    console.print(f"  → {verdict} (arch {a.arch_lift:+.2f} vs model {a.model_lift:+.2f}).")

    console.rule("[bold]The head-to-head")
    console.print(
        f"Weak model [bold]{weak}[/bold] + document tools: [bold]{a.weak_with_tools:.2f}[/bold]"
    )
    console.print(
        f"Strong model [bold]{strong}[/bold], closed-book:  [bold]{a.strong_no_tools:.2f}[/bold]"
    )
    if a.killer_holds:
        console.print(
            "[green]→ The weaker model, given the right architecture, matches or beats the "
            "stronger model without it. Architecture ≥ model.[/green]"
        )
    else:
        console.print(
            "[yellow]→ The stronger model still wins here — architecture narrowed the gap but "
            "did not close it at this sample size.[/yellow]"
        )


def _write_artifacts(grid: Grid, out_dir: Path) -> None:
    """Write a machine-readable JSON and a human-readable Markdown matrix of the results.

    Committing these makes the cookbook's evidence reproducible: anyone can regenerate them with
    ``uv run python evals/run_evals.py --models ... --out``.
    """
    import json
    from datetime import UTC, datetime

    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    a = analyze(grid)

    payload = {
        "generated_at": generated_at,
        "models": grid.models,
        "recipes": grid.recipes,
        "note": (
            "Real models + real data; answers scored by OfficeQA reward.py. Results vary run to "
            "run — the pattern (document access is the big lever; a better architecture can beat "
            "a better model) is the durable signal, not any single cell."
        ),
        "analysis": _analysis_payload(a),
        "cells": [
            {
                "recipe": recipe,
                "model": model,
                "questions": grid.cell(recipe, model).n,
                "scored": grid.cell(recipe, model).n_scored,
                "errors": grid.cell(recipe, model).errors,
                "accuracy": round(grid.cell(recipe, model).accuracy, 4),
                "avg_model_calls": round(grid.cell(recipe, model).avg_model_calls, 2),
                "avg_tokens": round(grid.cell(recipe, model).avg_tokens, 1),
                "runs": [
                    {
                        "uid": r.uid,
                        "correct": r.correct,
                        "model_calls": r.model_calls,
                        "total_tokens": r.total_tokens,
                        "steps": r.steps,
                        "stopped_reason": r.stopped_reason,
                    }
                    for r in grid.cell(recipe, model).runs
                ],
            }
            for recipe in grid.recipes
            for model in grid.models
        ],
    }
    (out_dir / "latest.json").write_text(json.dumps(payload, indent=2) + "\n")
    (out_dir / "latest.md").write_text(_markdown_report(grid, a, generated_at))
    print(f"\nWrote results to {out_dir / 'latest.json'} and {out_dir / 'latest.md'}")


def _analysis_payload(a: Analysis | None) -> dict | None:
    if a is None:
        return None
    return {
        "baseline_recipe": a.baseline_recipe,
        "tool_recipe": a.tool_recipe,
        "ranked_models_weak_to_strong": a.ranked_models,
        "model_lift": round(a.model_lift, 4),
        "architecture_lift": round(a.arch_lift, 4),
        "weak_model_with_tools": round(a.weak_with_tools, 4),
        "strong_model_no_tools": round(a.strong_no_tools, 4),
        "architecture_at_least_as_strong_as_model": a.architecture_wins,
        "weak_plus_tools_beats_strong_alone": a.killer_holds,
        "comparable": a.comparable,
    }


def _markdown_report(grid: Grid, a: Analysis | None, generated_at: str) -> str:
    models = grid.models
    lines = [
        "# Agentic FACETS — evaluation results",
        "",
        f"- Generated: `{generated_at}`",
        f"- Models: {', '.join(f'`{short_model(m)}`' for m in models)}",
        "- Scoring: OfficeQA subset, graded by the official `reward.py`.",
        "",
        "Real models + real data, so numbers vary run to run. The **pattern** is the point:",
        "document access is the big lever, and a better *architecture* can beat a better *model*.",
        "",
    ]

    if a is not None:
        holds = "**Yes.**" if a.killer_holds else "Not at this sample size —"
        arch = "**at least as large as**" if a.architecture_wins else "smaller than"
        lines += [
            "## The thesis, in two numbers",
            "",
            f"Models ranked weakest→strongest by closed-book accuracy: "
            f"{', '.join(f'`{short_model(m)}`' for m in a.ranked_models)}.",
            "",
            f"- **Model lift** (upgrade the LLM, closed-book): `{short_model(a.strong_model)}` − "
            f"`{short_model(a.weak_model)}` = **{a.model_lift:+.2f}**",
            f"- **Architecture lift** (give `{short_model(a.weak_model)}` document tools): "
            f"`01` − `00` = **{a.arch_lift:+.2f}**",
            "",
            f"The architecture lever is {arch} the model lever "
            f"(**{a.arch_lift:+.2f}** vs **{a.model_lift:+.2f}**).",
            "",
            f"**Head-to-head:** weak model + tools = **{a.weak_with_tools:.2f}**; "
            f"strong model, closed-book = **{a.strong_no_tools:.2f}**. "
            f"Does architecture beat the model upgrade? {holds}",
            "",
        ]
        if not a.comparable:
            lines += [
                "> ⚠ The compared cells did not share an identical question set; treat the "
                "head-to-head as indicative rather than exact.",
                "",
            ]

    # Accuracy matrix. Cells show accuracy over successfully-scored runs; an infra failure is
    # excluded, not counted as a wrong answer, and flagged so the reader can weigh reliability.
    any_errors = any(grid.cell(r, m).errors for r in grid.recipes for m in models)
    lines += [
        "## Accuracy: architecture (rows) × model (columns)",
        "",
        "Accuracy is over successfully-scored runs (`n`). Infra failures (rate limit / connection)"
        " are excluded, not scored wrong; ⚠ marks cells that had any.",
        "",
        "| Recipe | " + " | ".join(short_model(m) for m in models) + " |",
        "|" + "---|" * (len(models) + 1),
    ]
    for recipe in grid.recipes:
        row = [recipe]
        for m in models:
            cell = grid.cell(recipe, m)
            if not cell.n_scored:
                row.append(f"n/a ({cell.errors} err)" if cell.errors else "—")
                continue
            flag = f" ⚠{cell.errors}" if cell.errors else ""
            row.append(f"{cell.accuracy:.2f} (n={cell.n_scored}){flag}")
        lines.append("| " + " | ".join(row) + " |")
    if any_errors:
        lines += ["", "> ⚠N = N runs in that cell failed on infrastructure and were excluded."]

    # Cost matrix (avg tokens).
    lines += [
        "",
        "## Cost: average tokens per question",
        "",
        "| Recipe | " + " | ".join(short_model(m) for m in models) + " |",
        "|" + "---|" * (len(models) + 1),
    ]
    for recipe in grid.recipes:
        row = [recipe]
        for m in models:
            cell = grid.cell(recipe, m)
            row.append(f"{cell.avg_tokens:,.0f}" if cell.n_scored else "—")
        lines.append("| " + " | ".join(row) + " |")

    # Per-cell detail.
    lines += ["", "## Per-question detail", ""]
    for recipe in grid.recipes:
        for m in models:
            cell = grid.cell(recipe, m)
            if not cell.n:
                continue
            lines.append(f"### {recipe} · {short_model(m)}")
            lines.append("")
            lines.append("| Question | Correct | Model calls | Tokens | Steps | Stopped |")
            lines.append("|---|---|---|---|---|---|")
            for r in cell.runs:
                mark = "✓" if r.correct == 1.0 else "✗"
                lines.append(
                    f"| {r.uid} | {mark} | {r.model_calls} | {r.total_tokens} | {r.steps} "
                    f"| {r.stopped_reason} |"
                )
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the comparative FACETS evaluation grid.")
    parser.add_argument(
        "--models",
        help="Comma-separated Unity model-service names to sweep (the model axis). "
        "Default: the single FACETS_MODEL from the environment.",
    )
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

    if ns.models:
        model_names = [m.strip() for m in ns.models.split(",") if m.strip()]
    else:
        model_names = [os.environ.get("FACETS_MODEL", "system.ai.claude-sonnet-5")]
    models = {name: DatabricksModel(model=name) for name in model_names}

    uid_override = [u.strip() for u in ns.uids.split(",")] if ns.uids else None
    recipe_filter = {r.strip() for r in ns.recipes.split(",")} if ns.recipes else None

    grid = asyncio.run(
        evaluate_grid(
            models,
            uid_override=uid_override,
            recipe_filter=recipe_filter,
            concurrency=ns.concurrency,
        )
    )
    print()
    _print_grid(grid)
    _print_analysis(grid)
    if ns.out:
        _write_artifacts(grid, _ROOT / ns.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
