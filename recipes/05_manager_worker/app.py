"""Recipe 05 — Manager–worker.

    Manager ──delegates──> researcher (finds figures) + calculator (does arithmetic)
    workers ──results──> Manager synthesizes the answer

Changed from the single document agent along one axis:

    Topology:  single-agent  ->  manager-worker

A manager agent owns the question and delegates focused subtasks to two specialist workers, each
running in its own isolated context with a *disjoint* toolset: a researcher that reads documents
(no arithmetic) and a calculator that only computes. Workers behave like intelligent tools; the
manager decomposes, delegates, and synthesizes, and stays responsible throughout (contrast
Recipe 06, handoff, where responsibility *moves*).

FACETS profile:
    F=closed-loop  A=advisory  C=model-directed
    E=planner-executor  T=manager-worker  S=request-local

Run it:
    uv run python recipes/05_manager_worker/app.py
    uv run python recipes/05_manager_worker/app.py --uid UID0056
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
# Repo root + src for `facets`; the recipe's own dir so `import agents` finds the sibling module
# whether this file is run directly or loaded by the eval harness.
sys.path[:0] = [str(_HERE), str(_ROOT), str(_ROOT / "src")]

import agents as workers  # sibling module: recipes/05_manager_worker/agents.py

from facets.agents import Agent, AgentResult, Budget, ExecutionContext, agent_as_tool
from facets.officeqa import FINAL_ANSWER_INSTRUCTION, OfficeQADataset, Question

MANAGER_PROMPT = f"""You are the lead analyst answering a Treasury Bulletin question. You do not
read documents or do arithmetic yourself. Instead you have two specialists you call as tools:
- delegate_to_researcher: give it a precise fact-finding task; it returns figures from the
  documents.
- delegate_to_calculator: give it numbers and an arithmetic task; it returns the exact result.

Decompose the question: first ask the researcher for the figures you need, then (if arithmetic is
required) ask the calculator to compute the result, then give the final answer. You remain
responsible for the answer. {FINAL_ANSWER_INSTRUCTION}"""


def build_manager(dataset: OfficeQADataset, question: Question, model) -> Agent:
    tools = [
        agent_as_tool(
            workers.researcher(model, dataset, question.source_files),
            name="delegate_to_researcher",
            description="Delegate a fact-finding task over the documents. Input: an instruction.",
        ),
        agent_as_tool(
            workers.calculator(model, dataset, question.source_files),
            name="delegate_to_calculator",
            description="Delegate an arithmetic task. Input: the numbers and the computation.",
        ),
    ]
    return Agent(
        name="manager",
        model=model,
        tools=tools,
        system_prompt=MANAGER_PROMPT,
        budget=Budget(max_steps=12),
    )


async def run(question: Question, dataset: OfficeQADataset, *, model) -> AgentResult:
    manager = build_manager(dataset, question, model)
    ctx = ExecutionContext(task_id=f"officeqa-{question.uid}")
    return await manager.run(question.question, ctx)


def main() -> None:
    import asyncio

    from recipes._common import build_model, load_question, parse_recipe_args, print_qa_result

    ns = parse_recipe_args("Recipe 05 — manager–worker")
    dataset, question = load_question(ns.uid, ns.subset)
    result = asyncio.run(run(question, dataset, model=build_model()))
    print_qa_result("Recipe 05 — Manager–worker", question, result)


if __name__ == "__main__":
    main()
