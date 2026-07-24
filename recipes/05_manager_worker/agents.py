"""Worker specialists for the manager–worker topology (document QA).

Each worker is an ordinary :class:`~facets.agents.Agent` with a *scoped* subset of capabilities
and a narrow system prompt. The manager (in ``app.py``) delegates to them via
:func:`~facets.agents.agent_as_tool`, so from the manager's perspective a specialist is just
another callable tool that happens to be intelligent.

Two workers, with deliberately disjoint capabilities:

* **researcher** — has the document tools (list/search/read) but NOT compute. Its job is to find
  and report the exact figures the manager asks for.
* **calculator** — has ONLY compute. Its job is exact arithmetic on figures the manager gives it.

Splitting "find the numbers" from "do the math" is the classic reason to reach for
manager–worker: each worker has a focused context and a minimal, safe toolset. The manager stays
responsible (contrast Recipe 06, handoff, where responsibility *moves*).
"""

from __future__ import annotations

from facets.agents import Agent, Budget
from facets.officeqa import build_document_tools


def researcher(model, dataset, source_files) -> Agent:
    """A worker that reads documents and reports figures — no arithmetic."""
    read_tools = [
        t
        for t in build_document_tools(dataset, source_files)
        if t.spec.name != "compute"
    ]
    return Agent(
        name="researcher",
        model=model,
        tools=read_tools,
        system_prompt=(
            "You are a research assistant. You are given a specific fact-finding task about the "
            "Treasury Bulletin documents. Use search_document and read_document to find the exact "
            "figures requested, and report them plainly with their rows and units. Do not do "
            "arithmetic — just report what the documents say. Be terse."
        ),
        budget=Budget(max_steps=8),
    )


def calculator(model, dataset, source_files) -> Agent:
    """A worker with only the compute tool — exact arithmetic, nothing else."""
    compute_only = [
        t
        for t in build_document_tools(dataset, source_files)
        if t.spec.name == "compute"
    ]
    return Agent(
        name="calculator",
        model=model,
        tools=compute_only,
        system_prompt=(
            "You are a calculator. You are given numbers and an arithmetic task. Use the compute "
            "tool to evaluate it exactly and report the result. Do not round unless asked."
        ),
        budget=Budget(max_steps=4),
    )
