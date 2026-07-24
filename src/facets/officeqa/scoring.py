"""FACETS scorers for OfficeQA, built on the official ``reward.py``.

The whole point of moving to OfficeQA is that task success becomes *real* — graded against
ground truth by the benchmark's own scorer — instead of true-by-construction. This module wraps
:func:`facets.officeqa.reward.score_answer` as a FACETS :class:`~facets.evaluation.Scorer` so the
eval harness treats it like any other scorer.

The scorer contract from ``reward.py``: the prediction must contain the answer inside a
``<FINAL_ANSWER>…</FINAL_ANSWER>`` tag, and matching is exact or within a numeric tolerance
(with unit awareness). Agents in this scenario are therefore instructed to end with that tag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from facets.evaluation import Score
from facets.officeqa.reward import extract_final_answer, score_answer

if TYPE_CHECKING:
    from facets.agents import AgentResult
    from facets.evaluation import EvalCase, Scorer


class _OfficeQAScorer:
    def __init__(self, name: str, tolerance: float):
        self.name = name
        self._tolerance = tolerance

    def __call__(self, case: EvalCase, result: AgentResult) -> Score:
        # Ground truth is carried on the case; the model's answer is the run's final text.
        ground_truth = str(case.metadata.get("answer", ""))
        if not ground_truth:
            return Score(self.name, 0.0, "no ground-truth answer on case")
        if result.hit_limit:
            return Score(self.name, 0.0, f"stopped: {result.stopped_reason}")

        value = score_answer(ground_truth, result.answer, self._tolerance)
        extracted = extract_final_answer(result.answer).strip()
        if not extracted:
            detail = "no <FINAL_ANSWER> tag in response"
        else:
            verdict = "correct" if value == 1.0 else "incorrect"
            detail = f"{verdict}: answered {extracted!r} vs truth {ground_truth!r}"
        return Score(self.name, value, detail)


def answer_correctness_scorer(tolerance: float = 0.01) -> Scorer:
    """Grade the final answer against OfficeQA ground truth via the official reward function.

    ``tolerance`` is the fractional numeric tolerance (default 1%) passed to ``score_answer``;
    text answers must match exactly regardless.
    """
    return _OfficeQAScorer("answer_correctness", tolerance)
