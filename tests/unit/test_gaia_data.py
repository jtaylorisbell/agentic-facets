"""Unit tests for GAIA dataset parsing — pure, offline, no network or parquet file.

These cover the row→question mapping, the self-contained/needs-web classification (which selects
the spike's target slice), and level/int coercion. The actual parquet read and HF download are the
live integration path and are not exercised here.
"""

from __future__ import annotations

import pytest

from facets.gaia.data import GAIADataset, GAIAQuestion, _row_to_question


def _row(**over) -> dict:
    row = {
        "task_id": "abc-123",
        "Question": "What is the answer?",
        "Level": "2",
        "Final answer": "egalitarian",
        "file_name": "",
        "file_path": "",
        "Annotator Metadata": {"Number of tools": "2", "Number of steps": "5", "Tools": "1. calc"},
    }
    row.update(over)
    return row


def test_row_to_question_maps_fields():
    q = _row_to_question(_row())
    assert q.task_id == "abc-123"
    assert q.uid == "abc-123"  # alias for OfficeQA symmetry
    assert q.answer == "egalitarian"
    assert q.level == 2
    assert q.num_tools == 2
    assert q.num_steps == 5
    assert not q.has_file
    assert q.source_files == ()


def test_level_coerces_from_string_and_garbage():
    assert _row_to_question(_row(Level="1")).level == 1
    assert _row_to_question(_row(Level=3)).level == 3
    assert _row_to_question(_row(Level="")).level == 0  # garbage -> 0, no crash


def test_annotator_ints_default_to_zero_on_garbage():
    q = _row_to_question(_row(**{"Annotator Metadata": {"Number of tools": "n/a"}}))
    assert q.num_tools == 0
    assert q.num_steps == 0


def test_file_ext_and_has_file():
    q = _row_to_question(_row(file_name="data.xlsx"))
    assert q.has_file
    assert q.file_ext == "xlsx"
    assert q.source_files == ("data.xlsx",)


def test_needs_web_from_annotator_tools():
    web_tools = {"Annotator Metadata": {"Tools": "1. Web browser\n2. Search engine"}}
    web = _row_to_question(_row(**web_tools))
    assert web.needs_web
    calc = _row_to_question(_row(**{"Annotator Metadata": {"Tools": "1. A calculator"}}))
    assert not calc.needs_web


def test_is_self_contained_requires_readable_file_and_no_web():
    # Readable file, no web -> self-contained (the spike target).
    q = _row_to_question(
        _row(file_name="sheet.xlsx", **{"Annotator Metadata": {"Tools": "1. Excel"}})
    )
    assert q.is_self_contained

    # Has a file but also needs the web -> not self-contained.
    q2 = _row_to_question(
        _row(file_name="sheet.xlsx", **{"Annotator Metadata": {"Tools": "1. Web browser"}})
    )
    assert not q2.is_self_contained

    # No file at all -> not self-contained (it's an open-web question).
    q3 = _row_to_question(_row(file_name=""))
    assert not q3.is_self_contained

    # A file we can't read (image) -> not self-contained for the text-only tier.
    q4 = _row_to_question(
        _row(file_name="chart.png", **{"Annotator Metadata": {"Tools": "1. Image recognition"}})
    )
    assert not q4.is_self_contained


def test_invalid_split_rejected():
    with pytest.raises(ValueError):
        GAIADataset(split="train")


def test_attachment_path_requires_a_file():
    ds = GAIADataset(split="validation")
    no_file = _row_to_question(_row(file_name=""))
    with pytest.raises(ValueError):
        ds.attachment_path(no_file)


def test_question_is_frozen():
    q = GAIAQuestion(
        task_id="t", question="q", answer="a", level=1, file_name="", num_tools=0, num_steps=0
    )
    with pytest.raises(Exception):  # noqa: B017 — frozen dataclass raises FrozenInstanceError
        q.level = 2  # type: ignore[misc]
