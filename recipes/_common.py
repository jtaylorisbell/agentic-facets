"""Shared helpers for the recipe apps.

Kept deliberately small: which OfficeQA question to run, building the (real) model, and printing
a result with its score. Recipe-specific logic lives in each recipe's own ``app.py`` so it can
be read top-to-bottom in isolation.

Every recipe answers real Treasury Bulletin questions with a real Databricks model — there is no
offline/fake path. Import this only after the recipe's ``app.py`` has put the repo root on the
path.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from facets.agents import AgentResult
    from facets.models import ModelProvider
    from facets.officeqa import OfficeQADataset, Question

# Default question for a one-off recipe run. UID0001 (1940 national-defense expenditures) needs a
# single document and one table lookup + sum — the simplest end-to-end demonstration.
DEFAULT_UID = "UID0001"


def parse_recipe_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--uid",
        default=DEFAULT_UID,
        help=f"OfficeQA question uid to answer (default {DEFAULT_UID}).",
    )
    parser.add_argument(
        "--subset",
        default="pro",
        choices=["pro", "full"],
        help="OfficeQA subset (default 'pro').",
    )
    return parser.parse_args()


def build_model() -> ModelProvider:
    """Build the Databricks-backed model from the environment (via the Unity AI Gateway)."""
    from facets.models import DatabricksModel

    return DatabricksModel()


def load_question(uid: str, subset: str = "pro") -> tuple[OfficeQADataset, Question]:
    from facets.officeqa import OfficeQADataset

    dataset = OfficeQADataset(subset)
    return dataset, dataset.get(uid)


def print_qa_result(title: str, question: Question, result: AgentResult) -> None:
    """Pretty-print a recipe result: the question, the model's answer, the score, and the trace."""
    from rich.console import Console

    from facets.officeqa import answer_correctness_scorer
    from facets.officeqa.reward import extract_final_answer

    console = Console()
    console.rule(f"[bold]{title}")
    console.print(f"Q ({question.uid}): {question.question}", markup=False)
    console.print(f"Ground truth: {question.answer}", markup=False)
    console.rule("[dim]Answer")
    console.print(result.answer or "(no answer)", markup=False)

    # Score the run with the official OfficeQA reward function.
    from facets.evaluation import EvalCase

    case = EvalCase(id=question.uid, goal=question.question, metadata={"answer": question.answer})
    score = answer_correctness_scorer()(case, result)
    extracted = extract_final_answer(result.answer).strip() if result.answer else ""

    console.rule("[dim]Score")
    verdict = "CORRECT" if score.value == 1.0 else "INCORRECT"
    line = f"{verdict}  (extracted {extracted!r} vs truth {question.answer!r})"
    console.print(line, markup=False)

    console.rule("[dim]Trace")
    summary = result.trace.summary()
    summary["stopped_reason"] = result.stopped_reason
    summary["steps"] = result.steps
    console.print(summary)
