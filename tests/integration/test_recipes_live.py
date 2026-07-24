"""Live integration test — runs a recipe end-to-end against the real model and real data.

This is the honest test: it exercises the whole stack (Databricks model via the gateway + the
OfficeQA corpus + a recipe + the official scorer). It requires credentials, so it SKIPS when they
are absent — CI without secrets stays green, and a developer with a configured ``.env`` gets real
coverage.

It asserts the pivot's structural guarantees (every recipe runs, produces a scored answer, and
records real usage), not a specific correctness score — the model is real and its answers vary.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "src")]

from facets.config import load_env  # noqa: E402

load_env()

_HAVE_CREDS = bool(os.environ.get("DATABRICKS_HOST") and os.environ.get("DATABRICKS_TOKEN"))
_HAVE_HF = bool(os.environ.get("HF_TOKEN"))

pytestmark = pytest.mark.skipif(
    not (_HAVE_CREDS and _HAVE_HF),
    reason="live test needs DATABRICKS_HOST/TOKEN and HF_TOKEN (set them in .env)",
)


def _load_run(recipe: str):
    app_path = REPO / "recipes" / recipe / "app.py"
    name = f"live_{recipe}"
    spec = importlib.util.spec_from_file_location(name, app_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.run


@pytest.mark.parametrize(
    "recipe,uid",
    [
        ("00_closed_book_baseline", "UID0121"),
        ("01_single_tool_agent", "UID0121"),
        ("02_routed_workflow", "UID0121"),
        ("05_manager_worker", "UID0121"),
    ],
)
async def test_recipe_runs_end_to_end(recipe, uid):
    from facets.evaluation import EvalCase
    from facets.models import DatabricksModel
    from facets.officeqa import OfficeQADataset, answer_correctness_scorer

    dataset = OfficeQADataset("pro")
    question = dataset.get(uid)
    run = _load_run(recipe)

    result = await run(question, dataset, model=DatabricksModel())

    # Structural guarantees, not a specific score:
    assert isinstance(result.answer, str)
    assert result.trace.model_calls >= 1
    # The scorer accepts it (0.0 or 1.0) without raising.
    case = EvalCase(id=uid, goal=question.question, metadata={"answer": question.answer})
    score = answer_correctness_scorer()(case, result)
    assert score.value in (0.0, 1.0)


async def test_closed_book_uses_exactly_one_model_call():
    dataset_run = _load_run("00_closed_book_baseline")
    from facets.models import DatabricksModel
    from facets.officeqa import OfficeQADataset

    dataset = OfficeQADataset("pro")
    question = dataset.get("UID0121")
    result = await dataset_run(question, dataset, model=DatabricksModel())
    # The baseline is one shot, no tools.
    assert result.trace.model_calls == 1
    assert result.trace.tool_calls == []
