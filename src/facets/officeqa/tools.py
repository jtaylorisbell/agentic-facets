"""Document tools for the OfficeQA scenario.

These are the real capabilities an agent uses to answer a Treasury Bulletin question. They read
the *actual* corpus documents (fetched and cached by :class:`~facets.officeqa.data.OfficeQADataset`)
— there is no fixture and no faking. The tools are:

* ``list_source_documents`` — which documents are in scope for this question.
* ``search_document`` — grep for lines matching a pattern (documents are long; this is how an
  agent finds the right table without reading everything).
* ``read_document`` — read a line window of a document.
* ``compute`` — evaluate an arithmetic expression (these questions are numeric-reasoning heavy,
  and models are unreliable at mental arithmetic, so we give them a calculator).

**Oracle retrieval.** OfficeQA ships the gold ``source_files`` for each question, and the tools
are *scoped to those documents*. That is deliberate: this cookbook teaches agent architecture
(Control, Topology, Execution, …), so we hand the agent the right documents and let the
architecture differences show up in how it *reasons over* them — not in whether it can solve the
separate retrieval problem. A production system would add a real retrieval tool over the full
697-document corpus; that is noted where it matters.

Because the tools must be scoped to one question's documents, they are built by
:func:`build_document_tools`, which closes each tool over the dataset and the allowed files.
"""

from __future__ import annotations

import ast
import operator
import re
from typing import TYPE_CHECKING

from facets.tools import Tool, tool

if TYPE_CHECKING:
    from facets.officeqa.data import OfficeQADataset

# Cap how much text a single read returns, so one tool call cannot blow the context window on a
# 3,000-line document. The agent pages through with start_line instead.
_MAX_READ_LINES = 120
_MAX_SEARCH_HITS = 40


def build_document_tools(
    dataset: OfficeQADataset, source_files: tuple[str, ...]
) -> list[Tool]:
    """Build the document toolset scoped to one question's ``source_files``.

    Every tool is closed over ``dataset`` (for real reads) and ``source_files`` (the oracle
    scope). Reading a file outside the scope returns a soft error naming what is available, so a
    confused model is corrected rather than allowed to wander the whole corpus.
    """
    allowed = tuple(_normalize(name) for name in source_files)

    def _resolve(source_file: str) -> str:
        name = _normalize(source_file)
        if name not in allowed:
            available = ", ".join(allowed)
            raise ValueError(
                f"'{source_file}' is not in scope for this question. Available documents: "
                f"{available}."
            )
        return name

    @tool(name="list_source_documents")
    async def list_source_documents() -> list[str]:
        """List the Treasury Bulletin documents available for answering this question."""
        return list(allowed)

    @tool(name="search_document")
    async def search_document(source_file: str, pattern: str, context_lines: int = 2) -> dict:
        """Search one document for lines matching a (case-insensitive) substring or regex.

        Returns each matching line plus ``context_lines`` lines on either side, so you can usually
        read the answer straight from the search result without a separate read_document call.
        Every line is labelled with its line number. Use this first to locate the right table or
        figure. ``source_file`` must be one of the documents from list_source_documents.
        """
        name = _resolve(source_file)
        lines = dataset.read_document(name).splitlines()
        try:
            matcher = re.compile(pattern, re.IGNORECASE)
        except re.error:
            # Treat an invalid regex as a plain case-insensitive substring search.
            matcher = re.compile(re.escape(pattern), re.IGNORECASE)

        ctx = max(0, min(int(float(context_lines)), 6))
        hits = []
        for i, line in enumerate(lines):
            if matcher.search(line):
                lo = max(0, i - ctx)
                hi = min(len(lines), i + ctx + 1)
                window = {str(j): lines[j] for j in range(lo, hi)}
                hits.append({"line": i, "text": line.strip(), "context": window})
                if len(hits) >= _MAX_SEARCH_HITS:
                    break
        return {
            "source_file": name,
            "pattern": pattern,
            "match_count": len(hits),
            "matches": hits,
            "truncated": len(hits) >= _MAX_SEARCH_HITS,
        }

    @tool(name="read_document")
    async def read_document(source_file: str, start_line: int = 0, max_lines: int = 60) -> dict:
        """Read a window of a document, starting at ``start_line`` (0-indexed).

        Documents are long, so reads are capped; page through with ``start_line``. ``source_file``
        must be one of the documents from list_source_documents.
        """
        name = _resolve(source_file)
        lines = dataset.read_document(name).splitlines()
        # Defensive: coercion in the tool layer should have made these ints, but a model may
        # still slip through an odd type. int(float(...)) accepts "128" and "128.0" alike.
        start = max(0, int(float(start_line)))
        count = min(max(1, int(float(max_lines))), _MAX_READ_LINES)
        window = lines[start : start + count]
        numbered = {str(start + i): line for i, line in enumerate(window)}
        return {
            "source_file": name,
            "total_lines": len(lines),
            "start_line": start,
            "returned_lines": len(window),
            "lines": numbered,
            "more": start + count < len(lines),
        }

    @tool(name="compute")
    async def compute(expression: str) -> dict:
        """Evaluate an arithmetic expression, e.g. '406 + 462 + 500' or '(689 - 574) / 574 * 100'.

        Supports + - * / // % ** and parentheses. Use this for exact arithmetic instead of doing
        it in your head — these questions demand precise numbers.
        """
        try:
            value = _safe_eval(expression)
        except Exception as exc:  # noqa: BLE001 — surfaced as a soft error to the agent
            return {"expression": expression, "error": f"{type(exc).__name__}: {exc}"}
        return {"expression": expression, "result": value}

    return [list_source_documents, search_document, read_document, compute]


def _normalize(source_file: str) -> str:
    name = source_file.strip()
    return name if name.endswith(".txt") else f"{name}.txt"


# --- Safe arithmetic evaluator --------------------------------------------------------------
# A tiny AST-walking calculator. We do NOT use eval(): the model controls this string, and eval
# would be a code-execution hole. Only numeric literals and the operators below are allowed.

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _safe_eval(expression: str) -> float:
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree.body)


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("Only numbers and + - * / // % ** operators are allowed.")
