"""Integration test for the comparative eval harness.

Guards the cookbook's headline result: every recipe solves the incident (task success 1.0)
and cost grows monotonically with architectural complexity.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_runner():
    path = REPO / "evals" / "run_evals.py"
    spec = importlib.util.spec_from_file_location("run_evals", path)
    module = importlib.util.module_from_spec(spec)
    # Register before exec: run_evals defines a dataclass, whose decorator resolves annotations
    # via sys.modules[cls.__module__]. Without this, module creation raises AttributeError.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def test_all_recipes_pass_and_cost_is_monotonic():
    runner = _load_runner()
    reports = await runner.evaluate_all()

    by_recipe = {r.recipe: r for r in reports}
    # The three shipped recipes are discovered.
    assert set(by_recipe) == {
        "00_deterministic_baseline",
        "01_single_tool_agent",
        "05_manager_worker",
    }

    # All succeed at the task with correct tool use.
    for r in reports:
        assert r.score("task_success") == 1.0, r.recipe
        assert r.score("tool_correctness") == 1.0, r.recipe

    # Cost escalates with complexity — the framework's thesis, as a regression guard.
    calls = [
        by_recipe["00_deterministic_baseline"].model_calls,
        by_recipe["01_single_tool_agent"].model_calls,
        by_recipe["05_manager_worker"].model_calls,
    ]
    assert calls == sorted(calls)
    assert calls[0] == 0 < calls[1] < calls[2]
