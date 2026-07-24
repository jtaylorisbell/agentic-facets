"""Recipe 02 — Routed workflow.

    Incident -> Classify -> Dispatch to a predefined specialist -> Diagnosis

Same problem, changed from the single agent along two axes:

    Execution:  planner-executor  ->  router (classify, then branch)
    Topology:   single-agent      ->  router + specialists

A classifier (one model call) decides *which kind* of incident this is; then **code** dispatches
to a predefined specialist agent for that domain. The classification is model-assisted, but the
control flow — "if data-quality, run the data-quality specialist" — is written by the developer.
That's the tell that a router is usually still a *workflow*, not a full multi-agent system.

Contrast:
  * Router (here):     code picks a predefined specialist from a fixed menu.
  * Manager (Recipe 05): a model decomposes and delegates, staying responsible.
  * Handoff (Recipe 06): responsibility transfers to the specialist.

FACETS profile:
    F=closed-loop  A=advisory  C=code-directed
    E=router  T=router-specialists  S=request-local

Run it:
    uv run python recipes/02_routed_workflow/app.py           # offline, scripted
    uv run python recipes/02_routed_workflow/app.py --live     # live Databricks endpoint
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.agents import Agent, AgentResult, Budget, ExecutionContext
from facets.messages import Message
from facets.models import FakeModel, ModelProvider, call
from tools import (
    DEFAULT_PIPELINE,
    check_data_quality,
    get_pipeline_status,
    list_recent_deployments,
    query_logs,
    query_metrics,
)

# The fixed menu of incident categories the router chooses among.
CATEGORIES = ("data_quality", "infrastructure", "code_failure")

ROUTER_PROMPT = """You are an incident triage router. Classify the incident into exactly one
category: data_quality, infrastructure, or code_failure. Reply with only the category name."""


def _specialist(category: str, model: ModelProvider) -> Agent:
    """Build the predefined specialist agent for a category, each scoped to relevant tools."""
    if category == "data_quality":
        return Agent(
            name="data_quality_specialist",
            model=model,
            tools=[check_data_quality, query_logs, list_recent_deployments],
            system_prompt=(
                "You are a data-quality incident specialist. Inspect the data-quality checks and "
                "logs, tie the failure to any recent deployment, and report the root cause naming "
                "the specific column. Advisory only."
            ),
            budget=Budget(max_steps=6),
        )
    if category == "infrastructure":
        return Agent(
            name="infrastructure_specialist",
            model=model,
            tools=[get_pipeline_status, query_metrics],
            system_prompt=(
                "You are an infrastructure incident specialist. Inspect pipeline status and "
                "metrics and report whether this is an infrastructure/resource failure. Advisory."
            ),
            budget=Budget(max_steps=6),
        )
    return Agent(
        name="code_failure_specialist",
        model=model,
        tools=[query_logs, list_recent_deployments],
        system_prompt=(
            "You are a code-failure incident specialist. Inspect error logs and recent code "
            "deployments and report whether a code change caused the failure. Advisory."
        ),
        budget=Budget(max_steps=6),
    )


async def classify(pipeline: str, model: ModelProvider, ctx: ExecutionContext) -> str:
    """One model call that maps the incident to a category. Code uses the result to branch."""
    messages = [
        Message.system(ROUTER_PROMPT),
        Message.user(f"Classify the incident for pipeline '{pipeline}'."),
    ]
    with ctx.trace.span("router:classify", "model", step="classify"):
        resp = await model.complete(messages)
    ctx.trace.record_usage(resp.usage)
    text = (resp.text or "").strip().lower()
    for category in CATEGORIES:
        if category in text:
            return category
    return "data_quality"  # safe default if the classifier is unclear


def scripted_classifier() -> FakeModel:
    """Offline router: this incident is a data-quality failure."""
    return FakeModel(script=["data_quality"])


def scripted_specialist(pipeline: str) -> FakeModel:
    """Offline data-quality specialist plan."""
    return FakeModel(
        script=[
            [call("check_data_quality", pipeline=pipeline)],
            [call("query_logs", pipeline=pipeline, level="ERROR")],
            [call("list_recent_deployments", pipeline=pipeline)],
            (
                "Root cause: a schema mismatch on the `amount` column. The data-quality type "
                "check failed (expected DECIMAL, observed STRING); upstream deployment deploy-8842 "
                "changed `amount` to STRING. Recommend rolling back deploy-8842, then rerunning."
            ),
        ]
    )


async def run(
    pipeline: str = DEFAULT_PIPELINE, *, model: ModelProvider | None = None
) -> AgentResult:
    ctx = ExecutionContext(task_id=f"incident-{pipeline}")

    classifier_model: ModelProvider = model or scripted_classifier()
    category = await classify(pipeline, classifier_model, ctx)

    specialist_model: ModelProvider = model or scripted_specialist(pipeline)
    specialist = _specialist(category, specialist_model)

    goal = (
        f"The '{pipeline}' pipeline has failed and was triaged as a '{category}' incident. "
        "Investigate within your specialty and report the root cause."
    )
    result = await specialist.run(goal, ctx)
    # Prepend the routing decision so the trace/answer make the branch explicit.
    result.answer = f"[router → {category}] {result.answer}"
    return result


def main() -> None:
    import asyncio

    from recipes._common import live_model, parse_recipe_args, print_result

    ns = parse_recipe_args("Recipe 02 — routed workflow")
    pipeline = ns.pipeline or DEFAULT_PIPELINE
    model = live_model() if ns.live else None
    result = asyncio.run(run(pipeline, model=model))
    print_result("Recipe 02 — Routed workflow", result)


if __name__ == "__main__":
    main()
