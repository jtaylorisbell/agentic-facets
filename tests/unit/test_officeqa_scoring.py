"""Unit tests for the OfficeQA scorer wrapper — no network, no model.

The scorer wraps the vendored reward.py. These tests pin the contract the recipes rely on: the
answer must be inside <FINAL_ANSWER> tags, numeric tolerance applies, a truncated-but-correct run
still scores, and a missing answer scores zero.
"""

from __future__ import annotations

from types import SimpleNamespace

from facets.evaluation import EvalCase
from facets.officeqa import answer_correctness_scorer


def _result(answer: str, *, hit_limit: bool = False, stopped: str = "final"):
    return SimpleNamespace(answer=answer, hit_limit=hit_limit, stopped_reason=stopped)


def _case(answer: str):
    return EvalCase(id="q", goal="question", metadata={"answer": answer})


def test_correct_answer_in_tag():
    scorer = answer_correctness_scorer()
    score = scorer(_case("2"), _result("Reasoning… <FINAL_ANSWER>2</FINAL_ANSWER>"))
    assert score.value == 1.0


def test_wrong_answer():
    scorer = answer_correctness_scorer()
    assert scorer(_case("2"), _result("<FINAL_ANSWER>9</FINAL_ANSWER>")).value == 0.0


def test_numeric_tolerance():
    scorer = answer_correctness_scorer(tolerance=0.01)
    # 2602 vs 2610 is within 1%.
    assert scorer(_case("2,602"), _result("<FINAL_ANSWER>2610</FINAL_ANSWER>")).value == 1.0


def test_long_prose_without_tag_scores_zero():
    # reward.py falls back to the whole text when there's no <FINAL_ANSWER> tag, but its
    # direct-answer guard rejects long/multi-line prose — so an unwrapped essay scores zero.
    scorer = answer_correctness_scorer()
    essay = (
        "Let me work through this carefully.\n"
        "First I looked at the ownership survey table.\n"
        "After checking each category the count that exceeds the threshold is 2."
    )
    assert scorer(_case("2"), _result(essay)).value == 0.0


def test_truncated_but_correct_still_scores():
    # A planner that hit max_replans but produced the right final answer must still count.
    scorer = answer_correctness_scorer()
    score = scorer(
        _case("2"),
        _result("<FINAL_ANSWER>2</FINAL_ANSWER>", hit_limit=True, stopped="max_replans"),
    )
    assert score.value == 1.0


def test_no_ground_truth_scores_zero():
    scorer = answer_correctness_scorer()
    assert scorer(_case(""), _result("<FINAL_ANSWER>2</FINAL_ANSWER>")).value == 0.0
