"""GAIA scenario: real-world assistant tasks requiring multi-step tool use.

A *second* scenario alongside OfficeQA, mirroring its three-part contract so the recipes can run on
either benchmark (see ``docs/scenarios-gaia.md`` for the design and the honest cost). It provides:

* :class:`GAIADataset` — loads the gated GAIA question set (parquet) and fetches/caches a
  question's single attachment.
* :func:`build_gaia_tools` — a minimal file toolset (read_file / read_spreadsheet / read_pdf /
  compute) for the *self-contained* slice. GAIA's full web/vision/audio tooling is out of scope
  for the initial spike.
* :func:`gaia_correctness_scorer` — a FACETS scorer implementing GAIA's exact-match grading.

Unlike OfficeQA, GAIA is fundamentally a web-agent benchmark (~73% of questions need live search),
so only :meth:`GAIADataset.self_contained` questions are answerable with the tools here.

See https://huggingface.co/datasets/gaia-benchmark/GAIA (gated, no-reshare).
"""

from __future__ import annotations

from facets.gaia.data import GAIADataset, GAIAQuestion
from facets.gaia.scoring import gaia_correctness_scorer, score_gaia_answer
from facets.gaia.tools import build_gaia_tools

__all__ = [
    "GAIADataset",
    "GAIAQuestion",
    "build_gaia_tools",
    "gaia_correctness_scorer",
    "score_gaia_answer",
]

# The answer-format instruction every GAIA agent shares — the same <FINAL_ANSWER> tag OfficeQA
# uses, so the recipe contract is identical across scenarios. Phrasing follows GAIA's own
# guidance: a bare number (no units unless asked, no thousands commas), a short string, or a
# comma-separated list.
FINAL_ANSWER_INSTRUCTION = (
    "When you have the answer, end your reply with it wrapped in tags exactly like: "
    "<FINAL_ANSWER>value</FINAL_ANSWER>. Put only the bare value inside — a number (digits only, "
    "no '$', no thousands commas, no units unless the question asks for them), a short phrase, or "
    "a comma-separated list. Do not put anything after the closing tag."
)
