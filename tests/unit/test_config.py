"""Unit tests for env loading and the missing-credential error path — no network."""

from __future__ import annotations

import pytest

from facets.config import MissingCredential, require_env


def test_require_env_returns_value(monkeypatch):
    monkeypatch.setenv("FACETS_TEST_KEY", "hello")
    assert require_env("FACETS_TEST_KEY", why="w", how="h") == "hello"


def test_require_env_raises_with_instructions(monkeypatch):
    monkeypatch.delenv("FACETS_TEST_MISSING", raising=False)
    with pytest.raises(MissingCredential) as exc:
        require_env("FACETS_TEST_MISSING", why="Because reasons.", how="Do the thing.")
    message = str(exc.value)
    assert "FACETS_TEST_MISSING" in message
    assert "Because reasons." in message
    assert "Do the thing." in message


def test_officeqa_dataset_missing_token_is_actionable(monkeypatch):
    # With no HF_TOKEN, loading questions should raise the friendly credential error, not a raw
    # HTTP 401 — and crucially without needing the network.
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr("facets.config.load_env", lambda: None)

    from facets.officeqa.data import OfficeQADataset

    ds = OfficeQADataset("pro")
    with pytest.raises(MissingCredential):
        ds.questions()
