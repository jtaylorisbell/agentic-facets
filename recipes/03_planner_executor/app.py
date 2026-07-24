"""Recipe 03 — Planner–executor.

    Question -> plan document reads/computations -> execute -> inspect -> re-plan -> answer

Changed from the single document agent along two axes:

    Execution:  reactive tool loop      ->  plan-then-execute (explicit plan)
    State:      message history only     ->  an explicit, persisted task plan

Recipe 01's plan lives *implicitly* in the message history — the model decides the next tool one
step at a time. Here the plan is a **first-class artifact**: the planner emits a structured list
of steps up front (persisted to ``TaskState.plan``), code executes each via the document tools,
then the planner *inspects results and re-plans* — adding steps only when the evidence so far is
insufficient. That separation makes the plan inspectable, resumable, and easy to reason about —
the precondition for durable execution (Recipe 08, later).

FACETS profile:
    F=closed-loop  A=advisory  C=model-directed
    E=planner-executor  T=single-agent  S=durable-task (explicit plan)

Run it:
    uv run python recipes/03_planner_executor/app.py
    uv run python recipes/03_planner_executor/app.py --uid UID0056
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.agents import AgentResult, ExecutionContext
from facets.messages import Message
from facets.models import Usage
from facets.officeqa import (
    FINAL_ANSWER_INSTRUCTION,
    OfficeQADataset,
    Question,
    build_document_tools,
)
from facets.state import PlanStep, StepStatus, TaskState
from facets.tools import ToolRegistry

MAX_REPLANS = 4

PLANNER_PROMPT = """You are a research planner for Treasury Bulletin questions. Given the goal and
the results gathered so far, produce a JSON plan of the next steps. Reply with ONLY JSON:

  {"steps": [{"tool": "<tool name>", "arguments": {...}, "rationale": "<why>"}], "done": <bool>}

Set "done" to true (and "steps" to []) once the gathered evidence is enough to answer. Available
tools and their arguments:
  - list_source_documents: {}
  - search_document: {"source_file": "...", "pattern": "...", "context_lines": 2}
  - read_document: {"source_file": "...", "start_line": 0, "max_lines": 60}
  - compute: {"expression": "406 + 462 + 500"}
Plan incrementally — request only the steps you still need. Start by listing the documents."""

SYNTH_PROMPT = f"""You are answering a Treasury Bulletin question. Using the executed plan and its
results below, give the final answer. Be precise about units. {FINAL_ANSWER_INSTRUCTION}"""


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


async def _plan(model, state: TaskState, ctx: ExecutionContext, iteration: int) -> dict:
    """One planning/replanning model call. Sees the goal + results gathered so far."""
    gathered = {s.id: s.result for s in state.plan if s.status is StepStatus.DONE}
    messages = [
        Message.system(PLANNER_PROMPT),
        Message.user(
            f"Goal: {state.goal}\nResults so far: {json.dumps(gathered, default=str)[:6000]}\n"
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
    tool = registry.get(planned.get("tool", ""))
    if tool is None:
        step.status = StepStatus.FAILED
        step.result = f"Unknown tool '{planned.get('tool')}'."
        return
    args = dict(planned.get("arguments", {}))
    with ctx.trace.span(f"execute:{planned['tool']}", "tool", tool=planned["tool"]):
        result = await tool.execute({**args, "__call_id__": step.id}, ctx)
    step.status = StepStatus.FAILED if result.is_error else StepStatus.DONE
    step.result = result.content
    ctx.state.record_artifact(step.id, result.content)


async def run(question: Question, dataset: OfficeQADataset, *, model) -> AgentResult:
    registry = ToolRegistry(build_document_tools(dataset, question.source_files))
    state = TaskState(task_id=f"officeqa-{question.uid}", goal=question.question)
    ctx = ExecutionContext(task_id=state.task_id, state=state)

    step_counter = 0
    stopped_reason = "final"

    # Plan -> execute -> inspect/replan loop. The plan grows only when evidence is insufficient.
    for iteration in range(MAX_REPLANS + 1):
        plan = await _plan(model, state, ctx, iteration)
        new_steps = plan.get("steps", [])

        if not new_steps:
            if plan.get("done"):
                break
            stopped_reason = "no_progress"
            break

        for planned in new_steps:
            step_counter += 1
            step = PlanStep(
                id=f"step-{step_counter}",
                description=f"{planned.get('tool')}: {planned.get('rationale', '')}",
            )
            state.plan.append(step)
            state.checkpoint(f"planned {step.id}")
            await _execute_step(registry, step, planned, ctx)
            state.checkpoint(f"executed {step.id}")
    else:
        stopped_reason = "max_replans"

    # Synthesize the final answer from the executed plan.
    plan_results = {s.id: {"step": s.description, "result": s.result} for s in state.plan}
    messages = [
        Message.system(SYNTH_PROMPT),
        Message.user(
            f"Question: {state.goal}\n"
            f"Executed plan and results: {json.dumps(plan_results, default=str)[:12000]}"
        ),
    ]
    with ctx.trace.span("planner:synthesize", "model", step="synthesize"):
        resp = await model.complete(messages)
    ctx.trace.record_usage(resp.usage)

    return AgentResult(
        answer=resp.text or "",
        steps=len(state.plan),
        usage=Usage(
            input_tokens=ctx.trace.input_tokens,
            output_tokens=ctx.trace.output_tokens,
            model_calls=ctx.trace.model_calls,
        ),
        trace=ctx.trace,
        stopped_reason=stopped_reason,
    )


def main() -> None:
    import asyncio

    from recipes._common import build_model, load_question, parse_recipe_args, print_qa_result

    ns = parse_recipe_args("Recipe 03 — planner–executor")
    dataset, question = load_question(ns.uid, ns.subset)
    result = asyncio.run(run(question, dataset, model=build_model()))
    print_qa_result("Recipe 03 — Planner–executor", question, result)


if __name__ == "__main__":
    main()
