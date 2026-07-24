"""Integration tests: each recipe runs end-to-end, offline, and produces the right diagnosis.

These load each recipe's ``app.py`` by file path (recipe dirs start with digits, so they aren't
importable as normal packages) and call its uniform ``run()`` entrypoint with the default
scripted FakeModel. They assert the shared thesis: the same incident resolves the same way
across architectures, at different costs.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from facets.manifest import load_manifest

REPO = Path(__file__).resolve().parents[2]
RECIPES = REPO / "recipes"

# Auto-discover every runnable recipe (a directory with both app.py and facets.yaml).
RECIPE_DIRS = {
    d.name: d
    for d in sorted(RECIPES.iterdir())
    if (d / "app.py").exists() and (d / "facets.yaml").exists()
}

# The axis each recipe is meant to demonstrate — spot-checked against its manifest.
EXPECTED_AXIS = {
    "00_deterministic_baseline": lambda m: m.control.mode == "code-directed",
    "01_single_tool_agent": lambda m: m.topology.pattern == "single-agent",
    "02_routed_workflow": lambda m: m.execution.pattern == "router",
    "03_planner_executor": lambda m: m.execution.pattern == "planner-executor"
    and m.state.durability == "durable-task",
    "04_parallel_investigation": lambda m: m.execution.pattern == "parallel",
    "05_manager_worker": lambda m: m.topology.pattern == "manager-worker",
}


def _load_app(recipe_dir: Path):
    """Import a recipe's app.py under a unique module name (registered for dataclass support)."""
    app_path = recipe_dir / "app.py"
    name = f"recipe_{recipe_dir.name}_app"
    spec = importlib.util.spec_from_file_location(name, app_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", list(RECIPE_DIRS))
async def test_recipe_finds_root_cause(name):
    app = _load_app(RECIPE_DIRS[name])
    result = await app.run()
    assert result.stopped_reason == "final"
    assert "schema mismatch" in result.answer.lower()


@pytest.mark.parametrize("name", list(RECIPE_DIRS))
async def test_recipe_reads_the_logs(name):
    app = _load_app(RECIPE_DIRS[name])
    result = await app.run()
    # Every architecture must actually read the error logs to reach the diagnosis.
    assert "query_logs" in set(result.trace.tool_calls)


async def test_cost_ordering_across_architectures():
    """The framework's thesis: the deterministic baseline is free; agent recipes cost calls."""
    runs = {name: await _load_app(d).run() for name, d in RECIPE_DIRS.items()}

    # Deterministic baseline spends nothing on the model; every agent recipe does.
    assert runs["00_deterministic_baseline"].trace.model_calls == 0
    for name, r in runs.items():
        if name != "00_deterministic_baseline":
            assert r.trace.model_calls > 0, name

    # Manager-worker (sequential delegation) costs strictly more than the single agent.
    assert (
        runs["05_manager_worker"].trace.model_calls
        > runs["01_single_tool_agent"].trace.model_calls
    )


@pytest.mark.parametrize("name", list(RECIPE_DIRS))
def test_recipe_manifest_is_valid_and_matches(name):
    manifest = load_manifest(RECIPE_DIRS[name] / "facets.yaml")  # raises if schema-invalid
    check = EXPECTED_AXIS.get(name)
    assert check is not None, f"No expected-axis check registered for recipe {name}"
    assert check(manifest), f"{name} manifest did not match its demonstrated axis"
