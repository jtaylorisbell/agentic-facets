"""Recipe 02 — Routed workflow.

    Question -> classify its type -> dispatch to a predefined specialist -> answer

Changed from the single agent along two axes:

    Execution:  planner-executor  ->  router (classify, then branch)
    Topology:   single-agent      ->  router + specialists
    Control:    model-directed     ->  code-directed at the top level

A classifier (one model call) decides *which kind* of question this is — a direct lookup, a
multi-document comparison, or a numeric-reasoning question. Then **code** dispatches to a
predefined specialist agent tuned for that type (different prompt, different step budget). The
classification is model-assisted, but the branch is developer-written — the tell that a router
is usually still a *workflow*, not a full multi-agent system.

Contrast:
  * Router (here):       code picks a predefined specialist from a fixed menu.
  * Manager (Recipe 05): a model decomposes and delegates, staying responsible.
  * Handoff (Recipe 06): responsibility transfers to the specialist.

FACETS profile:
    F=closed-loop  A=advisory  C=code-directed
    E=router  T=router-specialists  S=request-local

Run it:
    uv run python recipes/02_routed_workflow/app.py
    uv run python recipes/02_routed_workflow/app.py --uid UID0056
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.agents import Agent, AgentResult, Budget, ExecutionContext
from facets.messages import Message
from facets.officeqa import (
    FINAL_ANSWER_INSTRUCTION,
    OfficeQADataset,
    Question,
    build_document_tools,
)

# The fixed menu of question types the router chooses among.
CATEGORIES = ("lookup", "multi_document", "numeric_reasoning")

ROUTER_PROMPT = """You are a triage router for Treasury Bulletin questions. Classify the question
into exactly one category:
- lookup: the answer is a single value read directly from one table in one document.
- multi_document: the answer requires combining figures from more than one document/year.
- numeric_reasoning: the answer requires multi-step arithmetic (sums, differences, growth rates)
  over figures in the document(s).
Reply with only the category name."""

# Each specialist shares the document tools but gets a prompt + budget tuned to its question type.
_SPECIALIST_PROMPTS = {
    "lookup": (
        "You answer direct-lookup questions. Use search_document to find the exact table row, "
        "read it, and report the value. It should take only a couple of tool calls."
    ),
    "multi_document": (
        "You answer questions that span multiple documents. List the source documents, gather the "
        "relevant figure from EACH, then combine them. Track which number came from which year."
    ),
    "numeric_reasoning": (
        "You answer questions that need arithmetic. Find the exact figures with search_document "
        "and read_document, then ALWAYS use the compute tool for sums, differences, and growth "
        "rates — never do the arithmetic in your head."
    ),
}
_SPECIALIST_BUDGET = {"lookup": 8, "multi_document": 16, "numeric_reasoning": 16}


async def classify(question: Question, model, ctx: ExecutionContext) -> str:
    """One model call mapping the question to a category. Code uses the result to branch."""
    messages = [Message.system(ROUTER_PROMPT), Message.user(question.question)]
    with ctx.trace.span("router:classify", "model", step="classify"):
        resp = await model.complete(messages)
    ctx.trace.record_usage(resp.usage)
    text = (resp.text or "").strip().lower()
    for category in CATEGORIES:
        if category in text:
            return category
    return "lookup"  # safe default if the classifier is unclear


def build_specialist(category: str, dataset: OfficeQADataset, question: Question, model) -> Agent:
    tools = build_document_tools(dataset, question.source_files)
    prompt = _SPECIALIST_PROMPTS[category]
    return Agent(
        name=f"{category}_specialist",
        model=model,
        tools=tools,
        system_prompt=f"{prompt}\n\n{FINAL_ANSWER_INSTRUCTION}",
        budget=Budget(max_steps=_SPECIALIST_BUDGET[category]),
    )


async def run(question: Question, dataset: OfficeQADataset, *, model) -> AgentResult:
    ctx = ExecutionContext(task_id=f"officeqa-{question.uid}")
    category = await classify(question, model, ctx)
    specialist = build_specialist(category, dataset, question, model)
    # The specialist shares ctx (and thus ctx.trace), so the router's classify call and the
    # specialist's tool calls roll up into one trace.
    result = await specialist.run(question.question, ctx)
    result.answer = f"[router → {category}] {result.answer}"
    return result


def main() -> None:
    import asyncio

    from recipes._common import build_model, load_question, parse_recipe_args, print_qa_result

    ns = parse_recipe_args("Recipe 02 — routed workflow")
    dataset, question = load_question(ns.uid, ns.subset)
    result = asyncio.run(run(question, dataset, model=build_model()))
    print_qa_result("Recipe 02 — Routed workflow", question, result)


if __name__ == "__main__":
    main()
