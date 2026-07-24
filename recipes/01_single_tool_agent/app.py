"""Recipe 01 — Tool-using single agent.

    Observe -> Choose Tool -> Inspect Result -> Continue or Finish

Same problem as Recipe 00, one axis changed:

    Control:  code-directed  ->  model-directed

The developer no longer writes the investigation graph. A single agent is given the read-only
tools and a goal, and the *model* decides which tool to call next, when it has enough evidence,
and how to summarize — bounded by ``max_steps`` so a confused model degrades to a truncated
answer instead of looping forever.

FACETS profile:
    F=closed-loop  A=advisory  C=model-directed
    E=planner-executor  T=single-agent  S=request-local

Run it:
    uv run python recipes/01_single_tool_agent/app.py            # offline, scripted FakeModel
    uv run python recipes/01_single_tool_agent/app.py --live     # live Databricks endpoint
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.agents import Agent, AgentResult, Budget, ExecutionContext
from facets.models import FakeModel, ModelProvider, call
from tools import DEFAULT_PIPELINE, read_only_tools

SYSTEM_PROMPT = """You are a data-pipeline incident investigator.
Investigate the failure using the available tools. Inspect logs, metrics, deployments, and
data-quality checks as needed. When you have enough evidence, stop calling tools and reply with
a concise root-cause diagnosis naming the specific column and the upstream change responsible.
Do not take any remediating action — you are advisory only."""


def scripted_model(pipeline: str) -> FakeModel:
    """A deterministic investigation plan for offline runs and tests.

    This is what a competent model *would* do: check status, read the error logs, confirm with
    data-quality, tie it to the recent deployment, then conclude. It mirrors the real
    tool-choosing loop without a network call.
    """
    return FakeModel(
        script=[
            [call("get_pipeline_status", pipeline=pipeline)],
            [call("query_logs", pipeline=pipeline, level="ERROR")],
            [call("check_data_quality", pipeline=pipeline)],
            [call("list_recent_deployments", pipeline=pipeline)],
            (
                "Root cause: a schema mismatch on the `amount` column. Upstream deployment "
                "deploy-8842 changed `amount` from DECIMAL to STRING, so orders_daily failed "
                "schema validation and wrote 0 rows. Recommend rolling back deploy-8842 (do not "
                "simply restart the job — the upstream schema is still wrong)."
            ),
        ]
    )


async def run(
    pipeline: str = DEFAULT_PIPELINE, *, model: ModelProvider | None = None
) -> AgentResult:
    model = model or scripted_model(pipeline)
    agent = Agent(
        name="investigator",
        model=model,
        tools=read_only_tools(),
        system_prompt=SYSTEM_PROMPT,
        budget=Budget(max_steps=8),
    )
    ctx = ExecutionContext(task_id=f"incident-{pipeline}")
    goal = f"The '{pipeline}' pipeline has failed. Investigate and report the root cause."
    return await agent.run(goal, ctx)


def main() -> None:
    import asyncio

    from recipes._common import live_model, parse_recipe_args, print_result

    ns = parse_recipe_args("Recipe 01 — single tool-using agent")
    pipeline = ns.pipeline or DEFAULT_PIPELINE
    model = live_model() if ns.live else scripted_model(pipeline)
    result = asyncio.run(run(pipeline, model=model))
    print_result("Recipe 01 — Single tool-using agent", result)


if __name__ == "__main__":
    main()
