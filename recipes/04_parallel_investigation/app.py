"""Recipe 04 — Parallel investigation.

                  ┌── read document A ─┐
    Question ─────┤   read document B  ├── Synthesize ── Answer
                  └── read document C ─┘

Changed from the single document agent along one axis:

    Execution:  sequential reads  ->  parallel fan-out / fan-in

Some OfficeQA questions span several documents (e.g. "compare the 1953 and 1954 figures"). Reading
those documents is **independent** — one does not need another's output — so we fan out one
investigator per source document, run them concurrently with ``asyncio.gather``, then fan in to a
synthesizer that combines their findings.

Each investigator runs in its own :class:`ExecutionContext` with its own trace (so concurrent
spans don't interleave under a shared object); the child traces are merged back into the parent
with ``Trace.absorb`` after the join.

The tradeoff this teaches: parallel fan-out cuts **latency** (wall-clock ≈ the slowest branch,
not the sum) but not **token cost** (every branch still runs). Use it when subtasks are
independent and latency matters. For a single-document question it degrades to one branch plus a
synthesis — correct, but no faster than Recipe 01.

FACETS profile:
    F=closed-loop  A=advisory  C=model-directed
    E=parallel  T=manager-worker  S=request-local

Run it:
    uv run python recipes/04_parallel_investigation/app.py --uid UID0004
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.agents import Agent, AgentResult, Budget, ExecutionContext
from facets.messages import Message
from facets.models import Usage
from facets.officeqa import (
    FINAL_ANSWER_INSTRUCTION,
    OfficeQADataset,
    Question,
    build_document_tools,
)
from facets.tracing import Trace

INVESTIGATOR_PROMPT = """You are extracting facts from ONE Treasury Bulletin document to help
answer a question. Search and read {source_file} for the figures the question needs, and report
what you find — the specific values, their rows, and their units. Do not try to compute the final
answer; just report the raw facts from this document clearly. Be terse."""

SYNTH_PROMPT = f"""You are the lead analyst. Several investigators each read one document and
reported the figures they found. Combine their findings to answer the question, doing any
arithmetic yourself and being careful about units. {FINAL_ANSWER_INSTRUCTION}"""


async def _investigate_document(
    dataset: OfficeQADataset, source_file: str, question: Question, model
) -> tuple[str, AgentResult]:
    """Run one per-document investigator in its own context + trace (safe to run concurrently)."""
    # Scope this investigator's tools to just its one document.
    tools = build_document_tools(dataset, (source_file,))
    agent = Agent(
        name=f"reader::{source_file}",
        model=model,
        tools=tools,
        system_prompt=INVESTIGATOR_PROMPT.format(source_file=source_file),
        budget=Budget(max_steps=8),
    )
    ctx = ExecutionContext(task_id=f"{question.uid}::{source_file}", trace=Trace())
    goal = f"Question: {question.question}\nReport the relevant figures from {source_file}."
    result = await agent.run(goal, ctx)
    return source_file, result


async def run(question: Question, dataset: OfficeQADataset, *, model) -> AgentResult:
    parent = Trace()
    docs = question.source_files or ()

    # Fan out: one investigator per source document, concurrently.
    with parent.span("parallel:fan_out", "step", branches=len(docs)):
        results = await asyncio.gather(
            *(_investigate_document(dataset, doc, question, model) for doc in docs)
        )

    # Fan in: merge each investigator's trace into the parent and collect findings.
    findings: dict[str, str] = {}
    for source_file, result in results:
        parent.absorb(result.trace)
        findings[source_file] = result.answer

    # Synthesize the merged findings into one answer.
    findings_text = "\n\n".join(f"From {doc}:\n{text}" for doc, text in findings.items())
    messages = [
        Message.system(SYNTH_PROMPT),
        Message.user(f"Question: {question.question}\n\nInvestigator findings:\n{findings_text}"),
    ]
    with parent.span("parallel:synthesize", "model", step="synthesize"):
        resp = await model.complete(messages)
    parent.record_usage(resp.usage)

    return AgentResult(
        answer=resp.text or "",
        steps=len(docs) + 1,
        usage=Usage(
            input_tokens=parent.input_tokens,
            output_tokens=parent.output_tokens,
            model_calls=parent.model_calls,
        ),
        trace=parent,
        stopped_reason="final",
    )


def main() -> None:
    from recipes._common import build_model, load_question, parse_recipe_args, print_qa_result

    ns = parse_recipe_args("Recipe 04 — parallel investigation")
    dataset, question = load_question(ns.uid, ns.subset)
    result = asyncio.run(run(question, dataset, model=build_model()))
    print_qa_result("Recipe 04 — Parallel investigation", question, result)


if __name__ == "__main__":
    main()
