"""Recipe 00 — Closed-book baseline.

    Question -> single model call (no tools, no documents) -> answer

This is the dumbest thing that could possibly work: ask the model the question directly and see
if it knows. No document access, no tools, no agency — one call, one shot. It is the control the
whole cookbook measures against.

For OfficeQA it will *usually be wrong*: the answers live in specific tables inside specific
Treasury Bulletins, and no model has those figures memorized. That failure is the point — it is
exactly what motivates giving the model document tools in Recipe 01.

FACETS profile:
    F=open-loop  A=advisory  C=code-directed
    E=sequential  T=none  S=request-local

Run it:
    uv run python recipes/00_closed_book_baseline/app.py
    uv run python recipes/00_closed_book_baseline/app.py --uid UID0030
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.agents import AgentResult
from facets.messages import Message
from facets.models import Usage
from facets.officeqa import FINAL_ANSWER_INSTRUCTION, Question
from facets.tracing import Trace

SYSTEM_PROMPT = f"""You are answering a question about U.S. Treasury Bulletin data from memory.
You have no documents to consult. Give your single best answer. If you do not know the exact
figure, give your best estimate rather than refusing. {FINAL_ANSWER_INSTRUCTION}"""


async def run(question: Question, dataset=None, *, model) -> AgentResult:
    """One model call, no tools. ``dataset`` is accepted for a uniform recipe signature but
    unused — the whole point of the baseline is that it never opens a document."""
    trace = Trace()
    messages = [Message.system(SYSTEM_PROMPT), Message.user(question.question)]
    with trace.span("baseline:answer", "model", step="answer"):
        response = await model.complete(messages)
    trace.record_usage(response.usage)

    return AgentResult(
        answer=response.text or "",
        steps=1,
        usage=Usage(
            input_tokens=trace.input_tokens,
            output_tokens=trace.output_tokens,
            model_calls=trace.model_calls,
        ),
        trace=trace,
        stopped_reason="final",
    )


def main() -> None:
    import asyncio

    from recipes._common import build_model, load_question, parse_recipe_args, print_qa_result

    ns = parse_recipe_args("Recipe 00 — closed-book baseline")
    dataset, question = load_question(ns.uid, ns.subset)
    result = asyncio.run(run(question, dataset, model=build_model()))
    print_qa_result("Recipe 00 — Closed-book baseline", question, result)


if __name__ == "__main__":
    main()
