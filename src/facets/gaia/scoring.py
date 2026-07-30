"""FACETS scorer for GAIA — a faithful reimplementation of the official exact-match grader.

GAIA grades an answer by exact match after normalization. We reimplement the leaderboard's
``scorer.py`` logic (rather than vendor it) because it is small, and reimplementing lets us fix a
known bug without diverging from the *intended* behavior.

The rules, matching the official scorer:

* **Numbers** — strip ``$``, ``%``, and ``,`` then ``float()``; compared with exact ``==`` (GAIA
  uses no numeric tolerance, unlike OfficeQA's 1%).
* **Lists** — a ground truth containing ``,`` or ``;`` is a list; split on ``[,;]`` and compare
  element-wise (numbers numerically, strings by normalized text). **Lengths must match.**
* **Strings** — remove all whitespace, lowercase, and (for scalars) strip punctuation; compare.

**The one deliberate divergence — a bug fix.** The official ``is_float(ground_truth)`` does not
strip commas before ``float()``, so a numeric ground truth written with a thousands separator
(``1,500``) is misclassified as a *list* ``[1, 500]`` and a correct ``1500`` scores wrong. Here,
:func:`_looks_numeric` strips separators before deciding number-vs-list, so ``1,500`` is treated
as the number it is. This is called out in ``docs/scenarios-gaia.md``.

As with OfficeQA, our recipes end their reply with ``<FINAL_ANSWER>…</FINAL_ANSWER>``; we extract
the tagged value and feed it to :func:`score_gaia_answer`, so the recipe contract is identical
across scenarios.
"""

from __future__ import annotations

import re
import string
from typing import TYPE_CHECKING

from facets.evaluation import Score
from facets.officeqa.reward import extract_final_answer

if TYPE_CHECKING:
    from facets.agents import AgentResult
    from facets.evaluation import EvalCase, Scorer


def _normalize_number(value: str) -> float:
    """Strip currency/percent/thousands separators and parse as float. Raises on non-numeric."""
    cleaned = value.replace("$", "").replace("%", "").replace(",", "").strip()
    return float(cleaned)


def _looks_numeric(value: str) -> bool:
    """Would this parse as a number once separators are stripped?"""
    try:
        _normalize_number(value)
        return True
    except (ValueError, TypeError):
        return False


# A single number written with thousands separators: 1,500 · 12,345,678 · 1,234.56 (optionally
# $/%-wrapped). A space or a non-3-digit group (e.g. "1000, 2000") does NOT match — that's a list.
_THOUSANDS_NUMBER = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")


def _is_thousands_number(value: str) -> bool:
    """True if ``value`` is a single comma-grouped number, not a comma-separated list."""
    return bool(_THOUSANDS_NUMBER.match(value.replace("$", "").replace("%", "").strip()))


def _normalize_str(value: str, *, remove_punct: bool = True) -> str:
    """Remove all whitespace, lowercase, and optionally strip punctuation."""
    no_ws = re.sub(r"\s", "", value)
    if remove_punct:
        no_ws = no_ws.translate(str.maketrans("", "", string.punctuation))
    return no_ws.lower()


def _split_list(value: str) -> list[str]:
    """Split a list-shaped answer on commas/semicolons into trimmed elements."""
    return [elem.strip() for elem in re.split(r"[,;]", value)]


def _is_list(ground_truth: str) -> bool:
    """A ground truth is a list only if it has a separator AND is not itself a number.

    This is the divergence from the official scorer: a numeric GT with a thousands separator
    (``1,500``) is a number, not a two-element list.
    """
    if not any(sep in ground_truth for sep in (",", ";")):
        return False
    # A comma-grouped single number (1,500) is NOT a list — the divergence from the official
    # scorer. But a plain comma-separated sequence (1000, 2000) IS a list, even though each part
    # is numeric, so we only exempt the well-formed thousands-number shape.
    return not _is_thousands_number(ground_truth)


def _elements_match(gt_elem: str, pred_elem: str) -> bool:
    """Compare one list element: numerically if the GT element is a number, else by text."""
    if _looks_numeric(gt_elem):
        try:
            return _normalize_number(pred_elem) == _normalize_number(gt_elem)
        except (ValueError, TypeError):
            return False
    # Element-wise string comparison keeps punctuation (matches the official scorer's remove_punct
    # =False for list elements), only collapsing whitespace and case.
    return _normalize_str(pred_elem, remove_punct=False) == _normalize_str(
        gt_elem, remove_punct=False
    )


def score_gaia_answer(ground_truth: str, prediction: str) -> float:
    """Return 1.0 if ``prediction`` matches ``ground_truth`` under GAIA's rules, else 0.0."""
    gt = (ground_truth or "").strip()
    pred = (prediction or "").strip()
    if not gt or not pred:
        return 0.0

    if _is_list(gt):
        gt_parts = _split_list(gt)
        pred_parts = _split_list(pred)
        if len(gt_parts) != len(pred_parts):
            return 0.0  # length mismatch is an immediate miss, as in the official scorer
        return 1.0 if all(
            _elements_match(g, p) for g, p in zip(gt_parts, pred_parts, strict=True)
        ) else 0.0

    if _looks_numeric(gt):
        try:
            return 1.0 if _normalize_number(pred) == _normalize_number(gt) else 0.0
        except (ValueError, TypeError):
            return 0.0

    # Plain string: whitespace-insensitive, case-insensitive, punctuation-stripped.
    return 1.0 if _normalize_str(pred) == _normalize_str(gt) else 0.0


class _GAIAScorer:
    name = "gaia_answer_correctness"

    def __call__(self, case: EvalCase, result: AgentResult) -> Score:
        ground_truth = str(case.metadata.get("answer", ""))
        if not ground_truth:
            return Score(self.name, 0.0, "no ground-truth answer on case")
        # Prefer the <FINAL_ANSWER> tag (our recipe contract). extract_final_answer returns the
        # whole reply when no tag is present, so detect the tag literally to report honestly.
        has_tag = "<FINAL_ANSWER>" in (result.answer or "")
        prediction = extract_final_answer(result.answer).strip()
        value = score_gaia_answer(ground_truth, prediction)
        if not has_tag:
            detail = f"no <FINAL_ANSWER> tag; scored full reply {prediction!r} vs {ground_truth!r}"
        else:
            verdict = "correct" if value == 1.0 else "incorrect"
            detail = f"{verdict}: answered {prediction!r} vs truth {ground_truth!r}"
        return Score(self.name, value, detail)


def gaia_correctness_scorer() -> Scorer:
    """Grade a GAIA answer against ground truth via the exact-match rules above (no tolerance)."""
    return _GAIAScorer()
