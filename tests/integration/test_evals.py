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


async def test_all_recipes_pass_and_costs_are_sane():
    runner = _load_runner()
    reports = await runner.evaluate_all()

    by_recipe = {r.recipe: r for r in reports}
    # All six shipped recipes are discovered by the harness.
    assert set(by_recipe) == {
        "00_deterministic_baseline",
        "01_single_tool_agent",
        "02_routed_workflow",
        "03_planner_executor",
        "04_parallel_investigation",
        "05_manager_worker",
    }

    # Every recipe succeeds at the task with correct tool use.
    for r in reports:
        assert r.score("task_success") == 1.0, r.recipe
        assert r.score("tool_correctness") == 1.0, r.recipe

    # The deterministic baseline is free; every agent recipe costs model calls.
    assert by_recipe["00_deterministic_baseline"].model_calls == 0
    for name, r in by_recipe.items():
        if name != "00_deterministic_baseline":
            assert r.model_calls > 0, name

    # Manager-worker (sequential delegation) costs strictly more than the single agent.
    assert (
        by_recipe["05_manager_worker"].model_calls
        > by_recipe["01_single_tool_agent"].model_calls
    )
