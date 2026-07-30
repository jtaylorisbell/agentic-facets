"""Spike: run the scenario-neutral Agent loop on a self-contained GAIA question.

This is a throwaway proof, not a committed recipe. It shows that the GAIA scenario package
(GAIADataset + build_gaia_tools + gaia_correctness_scorer + FINAL_ANSWER_INSTRUCTION) plugs into
the same Agent used by the OfficeQA recipes — i.e. the scenario abstraction holds against a real
second benchmark, using recipe 01's exact structure (single tool-using agent).

    uv run --with pyarrow python evals/spike_gaia.py                 # default self-contained task
    uv run --with pyarrow python evals/spike_gaia.py --task 389793a7 # a specific task_id prefix
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

from facets.agents import Agent, Budget, ExecutionContext  # noqa: E402
from facets.evaluation import EvalCase  # noqa: E402
from facets.gaia import (  # noqa: E402
    FINAL_ANSWER_INSTRUCTION,
    GAIADataset,
    build_gaia_tools,
    gaia_correctness_scorer,
)
from facets.models import DatabricksModel  # noqa: E402

# The same shape as recipe 01's system prompt, retargeted from Treasury Bulletins to GAIA's
# attachment-grounded tasks. This is the prompt a scenario seam would supply per-scenario.
SYSTEM_PROMPT = f"""You are a meticulous assistant answering a question whose answer is grounded in
a single attached file. Work methodically:
1. Call describe_attachment to see the file's name and type.
2. Read it with the appropriate tool (read_file / read_spreadsheet / read_pdf).
3. Reason step by step over what you read; use compute for any arithmetic.
Answer exactly what is asked — GAIA grades for exact equality. {FINAL_ANSWER_INSTRUCTION}"""


async def run_one(task_prefix: str | None) -> None:
    dataset = GAIADataset("validation")
    pool = dataset.self_contained()
    if not pool:
        print("No self-contained GAIA questions found.")
        return
    question = (
        next((q for q in pool if q.task_id.startswith(task_prefix)), pool[0])
        if task_prefix
        else pool[0]
    )

    agent = Agent(
        name="gaia_analyst",
        model=DatabricksModel(),
        tools=build_gaia_tools(dataset, question),
        system_prompt=SYSTEM_PROMPT,
        budget=Budget(max_steps=12),
    )
    ctx = ExecutionContext(task_id=f"gaia-{question.task_id}")
    result = await agent.run(question.question, ctx)

    case = EvalCase(
        id=question.task_id, goal=question.question, metadata={"answer": question.answer}
    )
    score = gaia_correctness_scorer()(case, result)

    print("=" * 72)
    print(f"task {question.task_id}  (Level {question.level}, file {question.file_name})")
    print(f"Q: {question.question[:300]}")
    print(f"ground truth: {question.answer!r}")
    print("-" * 72)
    print(f"answer: {result.answer}")
    print("-" * 72)
    print(f"SCORE: {'CORRECT' if score.value == 1.0 else 'INCORRECT'} — {score.detail}")
    print(
        f"trace: model_calls={result.trace.model_calls} "
        f"tokens={result.trace.total_tokens} tools={result.trace.tool_calls}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Spike: recipe-01-style agent on a GAIA question.")
    parser.add_argument("--task", help="task_id prefix to run (default: first self-contained).")
    ns = parser.parse_args()
    asyncio.run(run_one(ns.task))


if __name__ == "__main__":
    main()
