"""Unit tests for the OfficeQA document tools — no network, no model.

We build the tools against a fake in-memory dataset so these run offline and deterministically.
They cover the behavior the live model exercised (and broke) during the pivot: oracle scoping,
search-with-context, paging reads, the safe calculator, and argument coercion.
"""

from __future__ import annotations

import pytest

from facets.agents import ExecutionContext
from facets.officeqa.tools import _safe_eval, build_document_tools

_DOC = "\n".join(f"line {i}: value {i * 10}" for i in range(200))


class _FakeDataset:
    """Minimal stand-in for OfficeQADataset — returns a fixed document, no network."""

    def read_document(self, source_file: str) -> str:
        if source_file != "doc_a.txt":
            raise KeyError(source_file)
        return _DOC


def _tools():
    return {t.spec.name: t for t in build_document_tools(_FakeDataset(), ("doc_a.txt",))}


def ctx():
    return ExecutionContext(task_id="t")


async def test_list_source_documents_reports_scope():
    result = await _tools()["list_source_documents"].execute({}, ctx())
    assert result.content == ["doc_a.txt"]


async def test_read_document_paging():
    result = await _tools()["read_document"].execute(
        {"source_file": "doc_a.txt", "start_line": 5, "max_lines": 3}, ctx()
    )
    assert result.content["returned_lines"] == 3
    assert list(result.content["lines"].keys()) == ["5", "6", "7"]
    assert result.content["more"] is True


async def test_read_document_coerces_string_ints():
    # The live model sends "5"/"3" (strings) or 5.0 (floats); tools must not raise.
    result = await _tools()["read_document"].execute(
        {"source_file": "doc_a.txt", "start_line": "5", "max_lines": "3"}, ctx()
    )
    assert not result.is_error
    assert list(result.content["lines"].keys()) == ["5", "6", "7"]


async def test_search_document_returns_context_window():
    # Anchor the pattern so it matches exactly one line (line 3 -> "line 3: value 30").
    result = await _tools()["search_document"].execute(
        {"source_file": "doc_a.txt", "pattern": "^line 3: ", "context_lines": 1}, ctx()
    )
    assert result.content["match_count"] == 1
    match = result.content["matches"][0]
    assert match["line"] == 3
    assert set(match["context"].keys()) == {"2", "3", "4"}


async def test_out_of_scope_document_is_soft_error():
    result = await _tools()["read_document"].execute(
        {"source_file": "doc_b.txt", "start_line": 0}, ctx()
    )
    assert result.is_error
    assert "not in scope" in result.as_text()


async def test_compute_does_exact_arithmetic():
    result = await _tools()["compute"].execute({"expression": "406 + 462 + 500 + 574 + 689"}, ctx())
    assert result.content["result"] == 2631.0


async def test_compute_rejects_non_arithmetic():
    result = await _tools()["compute"].execute(
        {"expression": "__import__('os').system('ls')"}, ctx()
    )
    # Safe evaluator refuses; surfaced as an error field, not an exception.
    assert "error" in result.content


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("2 + 3 * 4", 14.0),
        ("(689 - 574) / 574 * 100", pytest.approx(20.0348, abs=1e-3)),
        ("-5 + 2", -3.0),
    ],
)
def test_safe_eval(expr, expected):
    assert _safe_eval(expr) == expected


def test_safe_eval_blocks_names_and_calls():
    for bad in ["os.system('x')", "open('f')", "1 if True else 2", "[1,2,3]"]:
        with pytest.raises((ValueError, SyntaxError, TypeError)):
            _safe_eval(bad)
