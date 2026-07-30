"""Unit tests for the GAIA scorer — pure, offline, no dataset or model.

These pin GAIA's exact-match contract (numbers with no tolerance, list length-must-match, string
normalization) and the one deliberate divergence from the official scorer: a numeric ground truth
written with a thousands separator (``1,500``) is a number, not a two-element list.
"""

from __future__ import annotations

from types import SimpleNamespace

from facets.evaluation import EvalCase
from facets.gaia.scoring import gaia_correctness_scorer, score_gaia_answer

# --- score_gaia_answer: the pure grading rules ----------------------------------------------


def test_number_exact_match():
    assert score_gaia_answer("42", "42") == 1.0
    assert score_gaia_answer("42", "42.0") == 1.0
    assert score_gaia_answer("42", "43") == 0.0


def test_number_strips_currency_and_percent():
    assert score_gaia_answer("1500", "$1,500") == 1.0
    assert score_gaia_answer("9.89", "9.89%") == 1.0


def test_number_has_no_tolerance():
    # Unlike OfficeQA (1% tolerance), GAIA is exact — 2610 != 2602.
    assert score_gaia_answer("2602", "2610") == 0.0


def test_comma_thousands_ground_truth_is_a_number_not_a_list():
    # The bug fix: GT "1,500" must be treated as the number 1500, so "1500" is correct.
    assert score_gaia_answer("1,500", "1500") == 1.0
    assert score_gaia_answer("1,500", "1,500") == 1.0
    # And a wrong number still misses.
    assert score_gaia_answer("1,500", "1501") == 0.0


def test_genuine_list_matches_elementwise():
    assert score_gaia_answer("apple, banana, cherry", "apple, banana, cherry") == 1.0
    # Order matters, element-wise.
    assert score_gaia_answer("apple, banana", "banana, apple") == 0.0


def test_list_length_mismatch_is_a_miss():
    assert score_gaia_answer("a, b, c", "a, b") == 0.0
    assert score_gaia_answer("a, b", "a, b, c") == 0.0


def test_list_with_numeric_elements():
    assert score_gaia_answer("1, 2, 3", "1, 2, 3") == 1.0
    assert score_gaia_answer("1, 2, 3", "1, 2, 4") == 0.0
    # Numeric elements compare by value, so a decimal-vs-int formatting difference is fine.
    assert score_gaia_answer("1000, 2000", "1000.0, 2000.0") == 1.0


def test_comma_is_ambiguous_between_list_and_thousands():
    # An inherent GAIA limitation (shared with the official scorer): a comma is both the list
    # separator and a thousands separator, so a list prediction that grabs thousands separators
    # (1,000) splits into too many elements and misses. Documented, not "fixed" — a model told to
    # emit a list should format elements without thousands commas.
    assert score_gaia_answer("1000, 2000", "1,000, 2,000") == 0.0


def test_semicolon_separated_list():
    assert score_gaia_answer("red; green; blue", "red; green; blue") == 1.0


def test_string_is_case_and_whitespace_and_punct_insensitive():
    assert score_gaia_answer("Egalitarian", "egalitarian") == 1.0
    assert score_gaia_answer("New York", "new  york") == 1.0
    assert score_gaia_answer("St. Louis", "st louis") == 1.0
    assert score_gaia_answer("egalitarian", "authoritarian") == 0.0


def test_empty_prediction_or_truth_scores_zero():
    assert score_gaia_answer("42", "") == 0.0
    assert score_gaia_answer("", "42") == 0.0


# --- the FACETS Scorer wrapper --------------------------------------------------------------


def _result(answer: str):
    return SimpleNamespace(answer=answer, hit_limit=False, stopped_reason="final")


def _case(answer: str):
    return EvalCase(id="task", goal="q", metadata={"answer": answer})


def test_scorer_extracts_final_answer_tag():
    scorer = gaia_correctness_scorer()
    reply = "I reason… <FINAL_ANSWER>egalitarian</FINAL_ANSWER>"
    score = scorer(_case("egalitarian"), _result(reply))
    assert score.value == 1.0
    assert "correct" in score.detail


def test_scorer_falls_back_to_full_reply_without_tag():
    scorer = gaia_correctness_scorer()
    # No tag: a bare exact answer still scores (fallback), with a detail noting the missing tag.
    score = scorer(_case("42"), _result("42"))
    assert score.value == 1.0
    assert "no <FINAL_ANSWER>" in score.detail


def test_scorer_no_ground_truth_scores_zero():
    scorer = gaia_correctness_scorer()
    assert scorer(_case(""), _result("<FINAL_ANSWER>42</FINAL_ANSWER>")).value == 0.0
