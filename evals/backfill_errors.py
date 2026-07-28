"""Re-run only the cells that failed on infrastructure, and merge them into latest.json.

The full grid records a run per (recipe, model, question). A run that failed on a rate limit or a
dropped connection is stored with a ``stopped_reason`` starting ``error:`` and excluded from
accuracy — but that leaves the sweep *incomplete* (some cells scored on n=3 instead of n=5). This
script closes that gap: it reloads the committed artifact, re-runs exactly the errored triples
with a fresh model, and rewrites latest.{json,md} using the harness's own scoring + rendering, so
the merged artifact is identical in shape to a clean full run.

    uv run python evals/backfill_errors.py --dry-run     # list what would re-run
    uv run python evals/backfill_errors.py --concurrency 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src"), str(_ROOT / "evals")]

from run_evals import (  # noqa: E402
    ERROR_PREFIX,
    RecipeRun,
    _discover,
    _load_run,
    _write_artifacts,
    short_model,
    summarize,
)

from facets.evaluation import EvalCase  # noqa: E402
from facets.officeqa import OfficeQADataset, answer_correctness_scorer  # noqa: E402

RESULTS = _ROOT / "evals" / "results"


def _load_runs(payload: dict) -> list[RecipeRun]:
    """Reconstruct every RecipeRun from the committed JSON, tagging recipe + model."""
    runs: list[RecipeRun] = []
    for cell in payload["cells"]:
        for r in cell["runs"]:
            runs.append(
                RecipeRun(
                    recipe=cell["recipe"],
                    model=cell["model"],
                    uid=r["uid"],
                    correct=r["correct"],
                    model_calls=r["model_calls"],
                    total_tokens=r["total_tokens"],
                    steps=r["steps"],
                    stopped_reason=r["stopped_reason"],
                )
            )
    return runs


async def main() -> int:
    parser = argparse.ArgumentParser(description="Re-run infra-errored cells and merge them in.")
    parser.add_argument("--concurrency", type=int, default=2, help="Max concurrent re-runs.")
    parser.add_argument("--dry-run", action="store_true", help="List the errored cells, don't run.")
    ns = parser.parse_args()

    payload = json.loads((RESULTS / "latest.json").read_text())
    all_runs = _load_runs(payload)
    errored = [r for r in all_runs if r.stopped_reason.startswith(ERROR_PREFIX)]

    if not errored:
        print("No errored cells in latest.json — the sweep is already complete.")
        return 0

    print(f"{len(errored)} errored cell(s) to re-run:")
    for r in errored:
        print(f"  {r.recipe:26s} {short_model(r.model):16s} {r.uid}  ({r.stopped_reason})")
    if ns.dry_run:
        return 0

    # Subset per recipe (from eval.yaml) and the recipe run() entrypoints — same as the harness.
    cfg_by_recipe = {recipe: cfg for recipe, _, cfg in _discover(None)}
    run_fns = {r.recipe: _load_run(_ROOT / "recipes" / r.recipe / "app.py") for r in errored}
    datasets: dict[str, OfficeQADataset] = {}
    scorer = answer_correctness_scorer()

    # One fresh model per distinct model name (its own client + auth refresh).
    from facets.models import DatabricksModel

    models = {r.model: DatabricksModel(model=r.model) for r in errored}

    sem = asyncio.Semaphore(ns.concurrency)
    done = 0
    total = len(errored)

    async def _rerun(old: RecipeRun) -> RecipeRun:
        nonlocal done
        subset = cfg_by_recipe.get(old.recipe, {}).get("subset", "pro")
        dataset = datasets.setdefault(subset, OfficeQADataset(subset))
        question = dataset.get(old.uid)
        async with sem:
            try:
                result = await run_fns[old.recipe](question, dataset, model=models[old.model])
                case = EvalCase(id=old.uid, goal=question.question,
                                metadata={"answer": question.answer})
                score = scorer(case, result)
                fresh = RecipeRun(
                    recipe=old.recipe,
                    model=old.model,
                    uid=old.uid,
                    correct=score.value,
                    model_calls=result.trace.model_calls,
                    total_tokens=result.trace.total_tokens,
                    steps=result.steps,
                    stopped_reason=result.stopped_reason,
                )
            except Exception as exc:  # noqa: BLE001 — still might fail; report, don't crash
                fresh = RecipeRun(
                    recipe=old.recipe, model=old.model, uid=old.uid, correct=0.0,
                    model_calls=0, total_tokens=0, steps=0,
                    stopped_reason=f"error: {type(exc).__name__}",
                )
        done += 1
        outcome = fresh.stopped_reason if fresh.is_error else f"{fresh.correct:.0f}"
        print(f"  [{done}/{total}] {fresh.recipe} · {short_model(fresh.model)} · "
              f"{fresh.uid} -> {outcome}", flush=True)
        return fresh

    fresh_runs = await asyncio.gather(*(_rerun(r) for r in errored))

    # Merge: replace each errored run with its fresh result, keyed by (recipe, model, uid).
    fresh_by_key = {(r.recipe, r.model, r.uid): r for r in fresh_runs}
    merged = [fresh_by_key.get((r.recipe, r.model, r.uid), r) for r in all_runs]

    still_bad = sum(1 for r in fresh_runs if r.is_error)
    grid = summarize(merged, recipes=payload["recipes"], models=payload["models"])
    _write_artifacts(grid, RESULTS)

    print(f"\nRe-ran {total} cell(s); {total - still_bad} now scored, {still_bad} still errored.")
    if still_bad:
        print("Re-run again to retry the remaining errors (they are rate limits, not real fails).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
