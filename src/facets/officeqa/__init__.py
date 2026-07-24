"""OfficeQA scenario: document-grounded question answering over U.S. Treasury Bulletins.

This package is the real-data scenario the cookbook's recipes investigate. It provides:

* :class:`OfficeQADataset` — loads the gated OfficeQA question set and fetches/caches the
  corpus documents (real reads, no fixture).
* :func:`build_document_tools` — the agent's capabilities over one question's documents
  (list / search / read / compute), scoped by oracle retrieval.
* :func:`answer_correctness_scorer` — a FACETS scorer wrapping the official ``reward.py``, so
  task success is graded against ground truth.

See https://huggingface.co/datasets/databricks/officeqa (gated, CC-BY-SA-4.0) and
https://github.com/databricks/officeqa (Apache-2.0 code).
"""

from __future__ import annotations

from facets.officeqa.data import OfficeQADataset, Question
from facets.officeqa.scoring import answer_correctness_scorer
from facets.officeqa.tools import build_document_tools

__all__ = [
    "OfficeQADataset",
    "Question",
    "answer_correctness_scorer",
    "build_document_tools",
]

# The instruction every OfficeQA agent shares: reason over the documents, then emit the answer in
# the tag the official scorer looks for. Kept here so all recipes phrase the contract identically.
FINAL_ANSWER_INSTRUCTION = (
    "When you have the answer, end your reply with the answer wrapped in tags exactly like: "
    "<FINAL_ANSWER>value</FINAL_ANSWER>. Put only the bare value inside the tags — a number "
    "(no '$', no commas unless the answer is a list), a date, or a short phrase — with any units "
    "the question asks for. Do not put anything after the closing tag."
)
