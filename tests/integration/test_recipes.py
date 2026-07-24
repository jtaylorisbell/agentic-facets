"""Integration tests: each recipe runs end-to-end, offline, and produces the right diagnosis.

These load each recipe's ``app.py`` by file path (recipe dirs start with digits, so they aren't
importable as normal packages) and call its uniform ``run()`` entrypoint with the default
scripted FakeModel. They assert the shared thesis: the same incident resolves the same way
across architectures, at different costs.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from facets.manifest import load_manifest

REPO = Path(__file__).resolve().parents[2]
RECIPES = REPO / "recipes"

RECIPE_DIRS = {
    "00": RECIPES / "00_deterministic_baseline",
    "01": RECIPES / "01_single_tool_agent",
    "05": RECIPES / "05_manager_worker",
}


def _load_app(recipe_dir: Path):
    """Import a recipe's app.py under a unique module name."""
    app_path = recipe_dir / "app.py"
    spec = importlib.util.spec_from_file_location(f"recipe_{recipe_dir.name}_app", app_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("key", ["00", "01", "05"])
async def test_recipe_finds_root_cause(key):
    app = _load_app(RECIPE_DIRS[key])
    result = await app.run()
    assert result.stopped_reason == "final"
    assert "schema mismatch" in result.answer.lower()


@pytest.mark.parametrize("key", ["00", "01", "05"])
async def test_recipe_exercises_evidence_tools(key):
    app = _load_app(RECIPE_DIRS[key])
    result = await app.run()
    tool_calls = set(result.trace.tool_calls)
    # Every architecture must actually read logs and data quality to reach the diagnosis.
    assert "query_logs" in tool_calls
    assert "check_data_quality" in tool_calls


async def test_cost_increases_with_architecture_complexity():
    """The framework's thesis, asserted: same answer, escalating cost 00 < 01 < 05."""
    r00 = await _load_app(RECIPE_DIRS["00"]).run()
    r01 = await _load_app(RECIPE_DIRS["01"]).run()
    r05 = await _load_app(RECIPE_DIRS["05"]).run()

    # Deterministic baseline spends nothing on the model.
    assert r00.trace.model_calls == 0
    # Model-directed control costs model calls; manager-worker costs strictly more than one agent.
    assert r00.trace.model_calls < r01.trace.model_calls < r05.trace.model_calls


@pytest.mark.parametrize("key", ["00", "01", "05"])
def test_recipe_manifest_is_valid_and_matches(key):
    recipe_dir = RECIPE_DIRS[key]
    manifest = load_manifest(recipe_dir / "facets.yaml")  # raises if schema-invalid
    # Spot-check the axis that each recipe is meant to demonstrate.
    expected = {
        "00": ("control", "code-directed", lambda m: m.control.mode),
        "01": ("topology", "single-agent", lambda m: m.topology.pattern),
        "05": ("topology", "manager-worker", lambda m: m.topology.pattern),
    }[key]
    _, want, getter = expected
    assert getter(manifest) == want
