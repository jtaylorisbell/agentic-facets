"""Recipe 01 — Tool-using single agent (document QA).

    Observe question -> choose a document tool -> inspect result -> continue or answer

The problem: answer a hard, document-grounded question from the OfficeQA benchmark (a real U.S.
Treasury Bulletin corpus). The answer is a specific number that lives in a table inside a long
document — the agent has to find the right table, read it, and often do exact arithmetic.

One agent is given the document tools (list / search / read / compute) scoped to the question's
source documents, and the *model* decides which tool to call next and when it can answer. This is
the baseline agent: model-directed control, a single context, read-only tools. Recipe 00 (the
closed-book baseline) shows what happens with no tools at all; the later recipes change one
FACETS axis at a time from here.

FACETS profile:
    F=closed-loop  A=advisory  C=model-directed
    E=planner-executor  T=single-agent  S=request-local

Run it:
    uv run python recipes/01_single_tool_agent/app.py            # default question (UID0001)
    uv run python recipes/01_single_tool_agent/app.py --uid UID0003
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.agents import Agent, AgentResult, Budget, ExecutionContext
from facets.officeqa import (
    FINAL_ANSWER_INSTRUCTION,
    OfficeQADataset,
    Question,
    build_document_tools,
)
from facets.officeqa.data import OfficeQADataset as _DS  # noqa: F401 (re-export convenience)

SYSTEM_PROMPT = f"""You are a meticulous research analyst answering a question from the U.S.
Treasury Bulletin. The answer is a specific value found inside the provided documents.

Work methodically:
1. Call list_source_documents to see which documents are in scope.
2. Use search_document to locate the relevant table or figure (documents are long).
3. Use read_document to read the exact rows you need.
4. Use compute for any arithmetic — do not do sums or percentages in your head.

Read carefully: these tables have footnotes, revised figures, and unit headers (e.g. "in
millions"). Match the units the question asks for. {FINAL_ANSWER_INSTRUCTION}"""


def build_agent(dataset: OfficeQADataset, question: Question, model) -> Agent:
    tools = build_document_tools(dataset, question.source_files)
    return Agent(
        name="analyst",
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        budget=Budget(max_steps=16),
    )


async def run(question: Question, dataset: OfficeQADataset, *, model) -> AgentResult:
    agent = build_agent(dataset, question, model)
    ctx = ExecutionContext(task_id=f"officeqa-{question.uid}")
    return await agent.run(question.question, ctx)


def main() -> None:
    import asyncio

    from recipes._common import build_model, load_question, parse_recipe_args, print_qa_result

    ns = parse_recipe_args("Recipe 01 — single document agent")
    dataset, question = load_question(ns.uid, ns.subset)
    result = asyncio.run(run(question, dataset, model=build_model()))
    print_qa_result("Recipe 01 — Single document agent", question, result)


if __name__ == "__main__":
    main()
