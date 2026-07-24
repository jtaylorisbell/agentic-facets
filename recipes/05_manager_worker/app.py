"""Recipe 05 — Manager–worker.

    Manager ──delegates──> Log / Metrics / Data-Quality / Deployment workers
    workers ──findings──> Manager synthesizes

Same problem again, one axis changed from the single agent:

    Topology:  single-agent  ->  manager-worker

A manager agent owns the incident and delegates focused subtasks to specialist worker agents,
each running in its own isolated context with a scoped set of tools. Workers behave like
intelligent tools; the manager decomposes, delegates, and synthesizes. The manager stays
responsible throughout (contrast Recipe 06, handoff, where responsibility *moves*).

FACETS profile:
    F=closed-loop  A=advisory  C=model-directed
    E=planner-executor  T=manager-worker  S=request-local

Run it:
    uv run python recipes/05_manager_worker/app.py           # offline, scripted
    uv run python recipes/05_manager_worker/app.py --live     # live Databricks endpoint
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
# Repo root + src for `tools`/`facets`; the recipe's own dir so `import agents` finds the
# sibling module whether this file is run directly or loaded by the eval harness.
sys.path[:0] = [str(_HERE), str(_ROOT), str(_ROOT / "src")]

import agents as workers  # sibling module: recipes/05_manager_worker/agents.py

from facets.agents import Agent, AgentResult, Budget, ExecutionContext, agent_as_tool
from facets.models import FakeModel, ModelProvider, call
from tools import DEFAULT_PIPELINE

MANAGER_PROMPT = """You are the incident manager for a data platform.
You do not investigate directly. Delegate focused subtasks to your specialist workers — the log,
metrics, data-quality, and deployment investigators — by calling their delegate tools. Gather
their findings, then synthesize a single root-cause diagnosis that names the specific column and
the upstream change responsible. You remain responsible for the final answer. Advisory only:
recommend remediation but do not take action."""


# The four specialists: (builder, delegate-tool name, description). One place to add a worker.
_SPECIALISTS = [
    (workers.log_worker, "delegate_to_log_investigator", "Delegate log/status analysis."),
    (workers.metrics_worker, "delegate_to_metrics_investigator", "Delegate metric analysis."),
    (workers.data_quality_worker, "delegate_to_data_quality_investigator", "Delegate DQ analysis."),
    (workers.deployment_worker, "delegate_to_deployment_investigator", "Delegate deploy analysis."),
]

# Maps each specialist to its key in the offline per-worker script dict.
_ROLE_KEYS = ["log", "metrics", "data_quality", "deployment"]


def scripted_manager() -> FakeModel:
    """Manager plan for offline runs: delegate to all four specialists, then synthesize."""
    return FakeModel(
        script=[
            [call("delegate_to_log_investigator", task="Find the key error in the logs.")],
            [call("delegate_to_metrics_investigator", task="Which metrics regressed?")],
            [call("delegate_to_data_quality_investigator", task="Which DQ checks failed?")],
            [call("delegate_to_deployment_investigator", task="Any suspicious deployment?")],
            (
                "Synthesis: orders_daily failed due to a schema mismatch on the `amount` column. "
                "The log worker found a SchemaValidationError (DECIMAL expected, STRING received); "
                "the data-quality worker confirmed the `amount` type check failed; the metrics "
                "worker shows rows_written fell to 0; the deployment worker traced it to "
                "deploy-8842, which changed `amount` to STRING upstream. Recommend rolling back "
                "deploy-8842, then rerunning — a plain job restart won't fix the upstream schema."
            ),
        ]
    )


def _scripted_worker_models(pipeline: str) -> dict:
    """Per-worker scripted models, so offline delegation is fully deterministic."""
    return {
        "log": workers.scripted_log_worker(pipeline),
        "metrics": workers.scripted_metrics_worker(pipeline),
        "data_quality": workers.scripted_data_quality_worker(pipeline),
        "deployment": workers.scripted_deployment_worker(pipeline),
    }


def _build_manager(
    manager_model: ModelProvider,
    worker_models: dict | ModelProvider,
) -> Agent:
    """Wrap each specialist as a delegate tool and give them to the manager.

    ``worker_models`` is either a per-role dict (offline, one scripted model each) or a single
    live model shared by every worker. Each specialist runs in its own isolated context.
    """
    tools = []
    for (build, tool_name, desc), role in zip(_SPECIALISTS, _ROLE_KEYS, strict=True):
        wm = worker_models[role] if isinstance(worker_models, dict) else worker_models
        tools.append(
            agent_as_tool(
                build(wm),
                name=tool_name,
                description=f"{desc} Input: a focused instruction string.",
            )
        )
    return Agent(
        name="incident_manager",
        model=manager_model,
        tools=tools,
        system_prompt=MANAGER_PROMPT,
        budget=Budget(max_steps=10),
    )


async def run(
    pipeline: str = DEFAULT_PIPELINE, *, model: ModelProvider | None = None
) -> AgentResult:
    if model is None:
        manager_model: ModelProvider = scripted_manager()
        worker_models: dict | ModelProvider = _scripted_worker_models(pipeline)
    else:
        # Live: the same provider drives the manager and all workers.
        manager_model = model
        worker_models = model

    manager = _build_manager(manager_model, worker_models)
    ctx = ExecutionContext(task_id=f"incident-{pipeline}")
    goal = (
        f"The '{pipeline}' pipeline has failed. Coordinate an investigation and report the "
        "root cause."
    )
    return await manager.run(goal, ctx)


def main() -> None:
    import asyncio

    from recipes._common import live_model, parse_recipe_args, print_result

    ns = parse_recipe_args("Recipe 05 — manager–worker")
    pipeline = ns.pipeline or DEFAULT_PIPELINE
    model = live_model() if ns.live else None
    result = asyncio.run(run(pipeline, model=model))
    print_result("Recipe 05 — Manager–worker", result)


if __name__ == "__main__":
    main()
