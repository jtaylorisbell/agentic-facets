"""Recipe 03 — Planner–executor.

    Goal -> Plan -> Execute steps -> Inspect -> Re-plan -> Finish

Same problem as the single tool agent, changed along two axes:

    Execution:  reactive tool loop      ->  plan-then-execute (explicit plan)
    State:      message history only     ->  an explicit, persisted task plan

The difference from Recipe 01 is subtle but important. Recipe 01's plan lives *implicitly* in the
message history — the model decides the next tool one step at a time. Here the plan is a
**first-class artifact**: the planner emits a structured list of steps up front (persisted to
``TaskState.plan``), code executes them, then the planner *inspects results and re-plans* —
adding steps only when the evidence so far is insufficient. That separation makes the plan
inspectable, resumable, and easy to reason about.

FACETS profile:
    F=closed-loop  A=advisory  C=model-directed
    E=planner-executor  T=single-agent  S=durable-task (explicit plan)

Run it:
    uv run python recipes/03_planner_executor/app.py           # offline, scripted
    uv run python recipes/03_planner_executor/app.py --live     # live Databricks endpoint
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.agents import AgentResult, ExecutionContext
from facets.messages import Message
from facets.models import FakeModel, ModelProvider, Usage
from facets.state import PlanStep, StepStatus, TaskState
from facets.tools import ToolRegistry
from tools import DEFAULT_PIPELINE, read_only_tools

MAX_REPLANS = 3

PLANNER_PROMPT = """You are an incident investigation planner. Given the goal and the results
gathered so far, produce a JSON plan of the next investigation steps. Reply with ONLY JSON:

  {"steps": [{"tool": "<tool name>", "arguments": {...}, "rationale": "<why>"}], "done": <bool>}

Set "done" to true (and "steps" to []) once the gathered evidence is enough to name the root
cause. Available tools: get_pipeline_status, query_logs, query_metrics, check_data_quality,
list_recent_deployments. Do not over-plan — request only the steps you still need."""

SYNTH_PROMPT = """You are an incident investigator. Using the executed plan and its results,
write a concise root-cause diagnosis naming the specific column and the upstream change
responsible. Advisory only — recommend remediation but take no action."""


def _parse_plan(text: str) -> dict:
    """Parse the planner's JSON reply, tolerating surrounding prose or code fences."""
    raw = (text or "").strip()
    if "```" in raw:
        raw = raw.split("```")[1].removeprefix("json").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return {"steps": [], "done": True}
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {"steps": [], "done": True}


async def _plan(
    model: ModelProvider, state: TaskState, ctx: ExecutionContext, iteration: int
) -> dict:
    """One planning/replanning model call. Sees the goal + results gathered so far."""
    gathered = {s.id: s.result for s in state.plan if s.status is StepStatus.DONE}
    messages = [
        Message.system(PLANNER_PROMPT),
        Message.user(
            f"Goal: {state.goal}\nResults so far: {json.dumps(gathered, default=str)}\n"
            "What are the next steps?"
        ),
    ]
    with ctx.trace.span(f"planner:plan[{iteration}]", "model", step="plan", iteration=iteration):
        resp = await model.complete(messages)
    ctx.trace.record_usage(resp.usage)
    return _parse_plan(resp.text or "")


async def _execute_step(
    registry: ToolRegistry, step: PlanStep, planned: dict, ctx: ExecutionContext
) -> None:
    """Execute one planned step by dispatching to its tool. Code, not a model, runs the step."""
    tool = registry.get(planned["tool"])
    if tool is None:
        step.status = StepStatus.FAILED
        step.result = f"Unknown tool '{planned['tool']}'."
        return
    args = dict(planned.get("arguments", {}))
    with ctx.trace.span(f"execute:{planned['tool']}", "tool", tool=planned["tool"]):
        result = await tool.execute({**args, "__call_id__": step.id}, ctx)
    step.status = StepStatus.FAILED if result.is_error else StepStatus.DONE
    step.result = result.content
    ctx.state.record_artifact(step.id, result.content)


async def run(
    pipeline: str = DEFAULT_PIPELINE, *, model: ModelProvider | None = None
) -> AgentResult:
    registry = ToolRegistry(read_only_tools())
    state = TaskState(
        task_id=f"incident-{pipeline}",
        goal=f"Investigate why the '{pipeline}' pipeline failed and name the root cause.",
    )
    ctx = ExecutionContext(task_id=state.task_id, state=state)

    planner_model: ModelProvider = model or scripted_planner(pipeline)
    step_counter = 0
    stopped_reason = "final"

    # Plan -> execute -> inspect/replan loop. The plan grows only when evidence is insufficient.
    for iteration in range(MAX_REPLANS + 1):
        plan = await _plan(planner_model, state, ctx, iteration)
        new_steps = plan.get("steps", [])

        if not new_steps:
            if plan.get("done"):
                break
            # No steps and not done: nothing left to try; stop to avoid spinning.
            stopped_reason = "no_progress"
            break

        for planned in new_steps:
            step_counter += 1
            step = PlanStep(
                id=f"step-{step_counter}",
                description=f"{planned['tool']}: {planned.get('rationale', '')}",
            )
            state.plan.append(step)
            state.checkpoint(f"planned {step.id}")
            await _execute_step(registry, step, planned, ctx)
            state.checkpoint(f"executed {step.id}")
    else:
        stopped_reason = "max_replans"

    # Synthesize the final diagnosis from the executed plan.
    synth_model: ModelProvider = model or scripted_synth()
    plan_results = {s.id: {"step": s.description, "result": s.result} for s in state.plan}
    messages = [
        Message.system(SYNTH_PROMPT),
        Message.user(f"Goal: {state.goal}\nExecuted plan: {json.dumps(plan_results, default=str)}"),
    ]
    with ctx.trace.span("planner:synthesize", "model", step="synthesize"):
        resp = await synth_model.complete(messages)
    ctx.trace.record_usage(resp.usage)
    answer = resp.text or ""

    return AgentResult(
        answer=answer,
        steps=len(state.plan),
        usage=Usage(
            input_tokens=ctx.trace.input_tokens,
            output_tokens=ctx.trace.output_tokens,
            model_calls=ctx.trace.model_calls,
        ),
        trace=ctx.trace,
        stopped_reason=stopped_reason,
    )


# --- Deterministic scripts for offline runs / tests ----------------------------------------


def scripted_planner(pipeline: str) -> FakeModel:
    """Offline planner: plan 3 steps, then (seeing no deploy evidence) re-plan to add it, then done.

    This mirrors real replanning: the initial plan gathers status/logs/DQ; on inspection the
    planner realizes it can't attribute the cause without deployment history and adds that step.
    """
    def steps(*specs):
        return json.dumps(
            {"steps": [{"tool": t, "arguments": a, "rationale": r} for t, a, r in specs],
             "done": False}
        )

    return FakeModel(
        script=[
            steps(
                ("get_pipeline_status", {"pipeline": pipeline}, "confirm the failure"),
                ("query_logs", {"pipeline": pipeline, "level": "ERROR"}, "find the error"),
                ("check_data_quality", {"pipeline": pipeline}, "see which checks failed"),
            ),
            steps(
                ("list_recent_deployments", {"pipeline": pipeline},
                 "attribute the schema change to a deployment"),
            ),
            json.dumps({"steps": [], "done": True}),
        ]
    )


def scripted_synth() -> FakeModel:
    return FakeModel(
        script=[
            (
                "Root cause: a schema mismatch on the `amount` column. The error log shows a "
                "SchemaValidationError (expected DECIMAL, received STRING) and the data-quality "
                "type check failed; deployment deploy-8842 changed `amount` to STRING upstream, "
                "which is when orders_daily began writing 0 rows. Recommend rolling back "
                "deploy-8842 and rerunning — a plain restart will not fix the upstream schema."
            )
        ]
    )


def main() -> None:
    import asyncio

    from recipes._common import live_model, parse_recipe_args, print_result

    ns = parse_recipe_args("Recipe 03 — planner–executor")
    pipeline = ns.pipeline or DEFAULT_PIPELINE
    model = live_model() if ns.live else None
    result = asyncio.run(run(pipeline, model=model))
    print_result("Recipe 03 — Planner–executor", result)


if __name__ == "__main__":
    main()
