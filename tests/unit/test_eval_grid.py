"""Unit tests for the model×architecture eval grid — pure aggregation, no network, no model.

These pin the thesis-critical logic in ``evals/run_evals.py``: given a grid of runs, do we
correctly compute *architecture lift* vs *model lift* and the "weak model + tools beats strong
model alone" head-to-head? The live sweep is expensive and non-deterministic; this logic is not,
so it gets real coverage here.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src"), str(_ROOT / "evals")]

import run_evals  # noqa: E402
from run_evals import (  # noqa: E402
    RecipeRun,
    analyze,
    evaluate_grid,
    short_model,
    summarize,
)

RECIPES = ["00_closed_book_baseline", "01_single_tool_agent", "05_manager_worker"]
WEAK = "system.ai.gpt-oss-20b"
STRONG = "system.ai.claude-sonnet-5"
UIDS = ["Q1", "Q2", "Q3", "Q4"]


def _runs(recipe: str, model: str, corrects: list[float]) -> list[RecipeRun]:
    """Build a cell's worth of runs with given correctness, over the shared UIDS."""
    return [
        RecipeRun(
            recipe=recipe,
            model=model,
            uid=UIDS[i],
            correct=c,
            model_calls=1,
            total_tokens=100,
            steps=1,
            stopped_reason="final",
        )
        for i, c in enumerate(corrects)
    ]


def _grid_from(spec: dict[tuple[str, str], list[float]]):
    runs: list[RecipeRun] = []
    models: list[str] = []
    for (recipe, model), corrects in spec.items():
        runs += _runs(recipe, model, corrects)
        if model not in models:
            models.append(model)
    return summarize(runs, recipes=RECIPES, models=models)


def test_short_model_strips_prefix():
    assert short_model("system.ai.gpt-oss-20b") == "gpt-oss-20b"
    assert short_model("system.ai.claude-sonnet-5") == "claude-sonnet-5"
    assert short_model("bare-name") == "bare-name"


def test_summarize_groups_into_cells():
    grid = _grid_from(
        {
            ("00_closed_book_baseline", WEAK): [0, 0, 1, 0],
            ("00_closed_book_baseline", STRONG): [0, 1, 1, 0],
        }
    )
    assert grid.cell("00_closed_book_baseline", WEAK).accuracy == 0.25
    assert grid.cell("00_closed_book_baseline", STRONG).accuracy == 0.5
    # A missing cell is empty, not an error.
    assert grid.cell("01_single_tool_agent", WEAK).n == 0


def test_analyze_needs_two_models():
    grid = _grid_from(
        {
            ("00_closed_book_baseline", STRONG): [0, 1, 1, 0],
            ("01_single_tool_agent", STRONG): [1, 1, 1, 1],
        }
    )
    assert analyze(grid) is None


def test_analyze_ranks_models_by_closed_book_accuracy():
    # STRONG knows more cold (0.50) than WEAK (0.25) -> WEAK is the weak model.
    grid = _grid_from(
        {
            ("00_closed_book_baseline", WEAK): [0, 0, 1, 0],
            ("00_closed_book_baseline", STRONG): [0, 1, 1, 0],
            ("01_single_tool_agent", WEAK): [1, 1, 1, 0],
            ("01_single_tool_agent", STRONG): [1, 1, 1, 1],
        }
    )
    a = analyze(grid)
    assert a is not None
    assert a.weak_model == WEAK
    assert a.strong_model == STRONG
    assert a.ranked_models == [WEAK, STRONG]


def test_analyze_computes_both_lifts():
    grid = _grid_from(
        {
            ("00_closed_book_baseline", WEAK): [0, 0, 0, 0],  # 0.00
            ("00_closed_book_baseline", STRONG): [0, 1, 0, 0],  # 0.25
            ("01_single_tool_agent", WEAK): [1, 1, 1, 0],  # 0.75
            ("01_single_tool_agent", STRONG): [1, 1, 1, 1],  # 1.00
        }
    )
    a = analyze(grid)
    assert a is not None
    # Model lift: upgrade weak->strong, closed-book: 0.25 - 0.00 = 0.25
    assert a.model_lift == 0.25
    # Architecture lift: give the weak model tools: 0.75 - 0.00 = 0.75
    assert a.arch_lift == 0.75
    assert a.architecture_wins  # 0.75 >= 0.25


def test_killer_comparison_holds_when_weak_plus_tools_beats_strong_alone():
    grid = _grid_from(
        {
            ("00_closed_book_baseline", WEAK): [0, 0, 0, 0],  # 0.00
            ("00_closed_book_baseline", STRONG): [0, 1, 0, 0],  # 0.25 strong, no tools
            ("01_single_tool_agent", WEAK): [1, 1, 0, 0],  # 0.50 weak, with tools
            ("01_single_tool_agent", STRONG): [1, 1, 1, 1],
        }
    )
    a = analyze(grid)
    assert a is not None
    assert a.weak_with_tools == 0.5
    assert a.strong_no_tools == 0.25
    assert a.killer_holds  # 0.50 >= 0.25 -> the weaker model, better wired, wins


def test_killer_comparison_fails_gracefully_when_model_still_wins():
    grid = _grid_from(
        {
            ("00_closed_book_baseline", WEAK): [0, 0, 0, 0],  # 0.00
            ("00_closed_book_baseline", STRONG): [1, 1, 1, 0],  # 0.75 strong, no tools
            ("01_single_tool_agent", WEAK): [1, 0, 0, 0],  # 0.25 weak, with tools
            ("01_single_tool_agent", STRONG): [1, 1, 1, 1],
        }
    )
    a = analyze(grid)
    assert a is not None
    assert not a.killer_holds  # 0.25 < 0.75


def test_evaluate_grid_fans_out_over_models_offline(monkeypatch):
    """The grid plumbing (model fan-out + per-cell model tagging) runs end-to-end offline.

    We stub recipe discovery so no real recipe/dataset/credentials are touched: each 'recipe'
    is a tiny async run() that just tags the answer with the model it was handed. This exercises
    the work-list construction and the (recipe, model, uid) → RecipeRun path — the part that only
    otherwise runs during the expensive live sweep.
    """
    import asyncio
    from types import SimpleNamespace

    class _FakeDataset:
        def get(self, uid):
            # answer "1" so the scorer marks it correct only when the recipe echoes <1>.
            return SimpleNamespace(uid=uid, question=f"q-{uid}", answer="1", source_files=())

    async def _fake_run(question, dataset, *, model):
        # `model` is the DatabricksModel-like object we injected; report which one ran this cell.
        trace = SimpleNamespace(model_calls=1, total_tokens=42)
        answer = f"<FINAL_ANSWER>{model.tag}</FINAL_ANSWER>"
        return SimpleNamespace(answer=answer, trace=trace, steps=1, stopped_reason="final")

    recipes = ["00_closed_book_baseline", "01_single_tool_agent"]

    def _fake_discover(recipe_filter):
        cfg = {"subset": "pro", "uids": ["Q1", "Q2"]}
        return [(r, Path(f"{r}/app.py"), cfg) for r in recipes]

    monkeypatch.setattr(run_evals, "_discover", _fake_discover)
    monkeypatch.setattr(run_evals, "_load_run", lambda _p: _fake_run)
    monkeypatch.setattr(run_evals, "OfficeQADataset", lambda _subset: _FakeDataset())

    # Two "models": one answers "1" (correct), one answers "0" (wrong) — so cells differ by model.
    models = {
        "system.ai.right": SimpleNamespace(tag="1"),
        "system.ai.wrong": SimpleNamespace(tag="0"),
    }

    grid = asyncio.run(evaluate_grid(models, concurrency=2))

    assert grid.recipes == recipes
    assert grid.models == ["system.ai.right", "system.ai.wrong"]
    # 2 recipes × 2 models × 2 uids = 8 runs, each tagged with the model that produced it.
    all_runs = [r for c in grid.cells.values() for r in c.runs]
    assert len(all_runs) == 8
    assert all(r.model in models for r in all_runs)
    # The "right" model scores 1.0 everywhere, the "wrong" model 0.0 — proving the model axis
    # actually threads the injected provider through to each cell.
    assert grid.accuracy("00_closed_book_baseline", "system.ai.right") == 1.0
    assert grid.accuracy("00_closed_book_baseline", "system.ai.wrong") == 0.0
    assert grid.accuracy("01_single_tool_agent", "system.ai.right") == 1.0


def test_analyze_flags_incomparable_question_sets():
    # Same recipe/models but the tool recipe ran different uids than the baseline.
    baseline_weak = _runs("00_closed_book_baseline", WEAK, [0, 0])
    baseline_strong = _runs("00_closed_book_baseline", STRONG, [0, 1])
    tool_weak = [
        RecipeRun("01_single_tool_agent", WEAK, uid, 1.0, 1, 100, 1, "final")
        for uid in ["OTHER1", "OTHER2"]  # different question set
    ]
    grid = summarize(
        baseline_weak + baseline_strong + tool_weak,
        recipes=RECIPES,
        models=[WEAK, STRONG],
    )
    a = analyze(grid)
    assert a is not None
    assert not a.comparable
