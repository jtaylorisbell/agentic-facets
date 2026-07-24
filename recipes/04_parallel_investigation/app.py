"""Recipe 04 — Parallel investigation.

                  ┌── Inspect Logs
    Incident ─────┼── Inspect Metrics      ──> Synthesize ──> Diagnosis
                  ├── Inspect Data Quality
                  └── Inspect Deployments

Same problem as manager–worker, changed along one axis:

    Execution:  sequential delegation  ->  parallel fan-out / fan-in

The four investigations are **independent** — none needs another's output — so we run them
concurrently with ``asyncio.gather`` instead of one after another, then fan in to a synthesizer.
Each investigator runs in its own :class:`ExecutionContext` with its own trace (so concurrent
spans don't interleave under a shared object); the child traces are merged back into the parent
with ``Trace.absorb`` after the join.

The tradeoff this recipe teaches: parallel fan-out cuts **latency** (wall-clock ≈ the slowest
branch, not the sum) but not **token cost** (every branch still runs). Use it when subtasks are
independent and latency matters.

FACETS profile:
    F=closed-loop  A=advisory  C=model-directed
    E=parallel  T=manager-worker  S=request-local

Run it:
    uv run python recipes/04_parallel_investigation/app.py           # offline, scripted
    uv run python recipes/04_parallel_investigation/app.py --live     # live Databricks endpoint
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.agents import Agent, AgentResult, Budget, ExecutionContext
from facets.messages import Message
from facets.models import FakeModel, ModelProvider, Usage, call
from facets.tracing import Trace
from tools import (
    DEFAULT_PIPELINE,
    check_data_quality,
    list_recent_deployments,
    query_logs,
    query_metrics,
)

SYNTH_PROMPT = """You are the lead incident investigator. You are given the independent findings
of four parallel investigators (logs, metrics, data-quality, deployments). Synthesize them into a
single root-cause diagnosis naming the specific column and the upstream change responsible.
Advisory only — recommend remediation but take no action."""


# Each investigator: (name, tools, system prompt). Independent — none depends on another.
INVESTIGATORS = [
    (
        "log_investigator",
        [query_logs],
        "Inspect the error logs for the pipeline and report the key error line. Be terse.",
    ),
    (
        "metrics_investigator",
        [query_metrics],
        "Inspect the pipeline metrics and report which regressed vs baseline. Be terse.",
    ),
    (
        "data_quality_investigator",
        [check_data_quality],
        "Inspect the data-quality checks and report which failed and on which column. Be terse.",
    ),
    (
        "deployment_investigator",
        [list_recent_deployments],
        "Inspect recent deployments and report the most suspicious one. Be terse.",
    ),
]


async def _run_investigator(
    name: str, tools, prompt: str, pipeline: str, model: ModelProvider
) -> tuple[str, AgentResult]:
    """Run one investigator in its own context + trace, so it is safe to run concurrently."""
    agent = Agent(
        name=name, model=model, tools=tools, system_prompt=prompt, budget=Budget(max_steps=4)
    )
    ctx = ExecutionContext(task_id=f"{name}-{pipeline}", trace=Trace())
    goal = f"Investigate the '{pipeline}' pipeline failure within your specialty."
    result = await agent.run(goal, ctx)
    return name, result


async def run(
    pipeline: str = DEFAULT_PIPELINE, *, model: ModelProvider | None = None
) -> AgentResult:
    parent = Trace()

    # Fan out: launch all investigators concurrently.
    scripts = scripted_investigators(pipeline)
    tasks = [
        _run_investigator(
            name, tools, prompt, pipeline, model or scripts[name]
        )
        for (name, tools, prompt) in INVESTIGATORS
    ]
    with parent.span("parallel:fan_out", "step", branches=len(tasks)):
        results = await asyncio.gather(*tasks)

    # Fan in: merge each investigator's trace into the parent and collect findings.
    findings: dict[str, str] = {}
    for name, result in results:
        parent.absorb(result.trace)
        findings[name] = result.answer

    # Synthesize the merged findings into one diagnosis.
    synth_model: ModelProvider = model or scripted_synth()
    messages = [
        Message.system(SYNTH_PROMPT),
        Message.user("Findings:\n" + "\n".join(f"- {k}: {v}" for k, v in findings.items())),
    ]
    with parent.span("parallel:synthesize", "model", step="synthesize"):
        resp = await synth_model.complete(messages)
    parent.record_usage(resp.usage)

    return AgentResult(
        answer=resp.text or "",
        steps=len(INVESTIGATORS) + 1,
        usage=Usage(
            input_tokens=parent.input_tokens,
            output_tokens=parent.output_tokens,
            model_calls=parent.model_calls,
        ),
        trace=parent,
        stopped_reason="final",
    )


# --- Deterministic scripts for offline runs / tests ----------------------------------------


def scripted_investigators(pipeline: str) -> dict[str, FakeModel]:
    """One scripted model per investigator; each calls its tool then reports a terse finding."""
    return {
        "log_investigator": FakeModel(
            script=[
                [call("query_logs", pipeline=pipeline, level="ERROR")],
                "SchemaValidationError on 'amount' (expected DECIMAL, got STRING).",
            ]
        ),
        "metrics_investigator": FakeModel(
            script=[
                [call("query_metrics", pipeline=pipeline)],
                "rows_written fell from 1.25M to 0; error_rate rose to 1.0.",
            ]
        ),
        "data_quality_investigator": FakeModel(
            script=[
                [call("check_data_quality", pipeline=pipeline)],
                "Failed: 'amount' type_match (expected DECIMAL, observed STRING).",
            ]
        ),
        "deployment_investigator": FakeModel(
            script=[
                [call("list_recent_deployments", pipeline=pipeline)],
                "deploy-8842 changed 'amount' from DECIMAL to STRING upstream.",
            ]
        ),
    }


def scripted_synth() -> FakeModel:
    return FakeModel(
        script=[
            (
                "Root cause: a schema mismatch on the `amount` column. The log and data-quality "
                "investigators independently found a DECIMAL→STRING type failure on `amount`; the "
                "metrics investigator shows rows_written collapsed to 0; the deployment "
                "investigator traced the change to deploy-8842 upstream. Recommend rolling back "
                "deploy-8842, then rerunning — a plain restart will not fix the upstream schema."
            )
        ]
    )


def main() -> None:
    from recipes._common import live_model, parse_recipe_args, print_result

    ns = parse_recipe_args("Recipe 04 — parallel investigation")
    pipeline = ns.pipeline or DEFAULT_PIPELINE
    model = live_model() if ns.live else None
    result = asyncio.run(run(pipeline, model=model))
    print_result("Recipe 04 — Parallel investigation", result)


if __name__ == "__main__":
    main()
