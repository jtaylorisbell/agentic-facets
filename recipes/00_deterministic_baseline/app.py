"""Recipe 00 — Deterministic baseline.

    Collect Inputs -> Query Logs -> Query Metrics -> Check Data Quality -> Summarize -> Return

The developer defines the entire execution graph; there is **no model and no agent**. This is
the control against which every later recipe is measured — it shows how far you get with plain
code before autonomy is *earned*.

FACETS profile:  F=open-loop  A=advisory  C=code-directed  E=sequential  T=none  S=request-local

Run it:
    uv run python recipes/00_deterministic_baseline/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the recipe independently runnable (`python recipes/00_.../app.py`) by putting the repo
# root (for `tools`) and `src/` (for `facets`) on the path.
_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.agents import AgentResult
from facets.models import Usage
from facets.tracing import Trace
from tools import DEFAULT_PIPELINE
from tools.data_quality import check_data_quality_raw
from tools.logs import query_logs_raw
from tools.metrics import query_metrics_raw
from tools.pipelines import get_pipeline_status_raw, list_recent_deployments_raw


def diagnose(pipeline: str, trace: Trace) -> str:
    """The fixed investigation pipeline. Pure code — every branch is written by the developer.

    Each tool call is wrapped in a trace span so a non-agentic baseline still produces the same
    kind of observability record the agent recipes do (making the eval table apples-to-apples).
    """

    def step(name: str):
        return trace.span(f"baseline:{name}", "tool", tool=name)

    with step("get_pipeline_status"):
        status = get_pipeline_status_raw(pipeline)
    with step("query_logs"):
        errors = query_logs_raw(pipeline, level="ERROR")
    with step("query_metrics"):
        metrics = query_metrics_raw(pipeline)
    with step("check_data_quality"):
        dq = check_data_quality_raw(pipeline)
    with step("list_recent_deployments"):
        deployments = list_recent_deployments_raw(pipeline)

    # Deterministic rule-based summary. No model judgement — just wiring facts together.
    if status["status"] != "FAILED" and dq["passed"]:
        return f"Pipeline '{pipeline}' is healthy (status={status['status']}). No action needed."

    failed_cols = ", ".join(sorted({c["column"] for c in dq["failed_checks"]})) or "none"
    rows = metrics["rows_written"]
    error_line = errors[0]["msg"] if errors else "no error line found"
    recent_deploy = deployments[0] if deployments else None

    lines = [
        f"Pipeline '{pipeline}' status: {status['status']}.",
        f"Rows written: {rows['latest']} (baseline {rows['baseline']}).",
        f"First error: {error_line}",
        f"Failed data-quality columns: {failed_cols}.",
    ]
    if recent_deploy:
        lines.append(
            f"Most recent deployment: {recent_deploy['id']} on {recent_deploy['service']} "
            f"— {recent_deploy['summary']}"
        )
    # The baseline can *report* a likely cause because the rule is hard-coded, but it cannot
    # reason about a novel failure the developer did not anticipate.
    if not dq["passed"] and "amount" in failed_cols:
        lines.append(
            "Likely cause: a schema mismatch on the 'amount' column, consistent with the "
            "recent upstream deployment."
        )
    return "\n".join(lines)


async def run(pipeline: str = DEFAULT_PIPELINE, *, model=None) -> AgentResult:
    """Common recipe entrypoint. ``model`` is accepted for a uniform signature but ignored —
    this recipe is deterministic by definition."""
    trace = Trace()
    answer = diagnose(pipeline, trace)
    return AgentResult(
        answer=answer,
        steps=0,
        usage=Usage(model_calls=0),
        trace=trace,
        stopped_reason="final",
    )


def main() -> None:
    import asyncio

    from rich.console import Console

    console = Console()
    result = asyncio.run(run())
    console.rule("[bold]Recipe 00 — Deterministic baseline")
    console.print(result.answer)
    console.rule("[dim]Trace")
    console.print(result.trace.summary())


if __name__ == "__main__":
    main()
