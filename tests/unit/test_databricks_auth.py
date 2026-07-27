"""Unit tests for Databricks auth resolution — pure priority logic, no network handshake.

These pin the rule that matters: OAuth is preferred, a static token is only a fallback, and the
resolver never silently produces nothing. The OAuth path is monkeypatched at the SDK boundary so
no real login happens; we assert *which* path was chosen and that the token provider is wired,
not that a real token comes back.
"""

from __future__ import annotations

import pytest

from facets import databricks_auth
from facets.config import MissingCredential
from facets.databricks_auth import resolve_auth


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Isolate from the developer's real .env / environment, and neutralize load_env so a repo
    # .env can't leak credentials into the test.
    for var in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_CONFIG_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(databricks_auth, "load_env", lambda: None)


def _stub_oauth(monkeypatch, token="oauth-tok", host="https://oauth-host"):
    """Replace the SDK-backed OAuth builder with a deterministic stub."""

    def _fake_oauth(h, profile):
        return databricks_auth.ResolvedAuth(
            host=(h or host).rstrip("/"),
            token_provider=lambda: token,
            method="oauth",
        )

    monkeypatch.setattr(databricks_auth, "_oauth_auth", _fake_oauth)


def test_profile_selects_oauth_even_when_static_token_present(monkeypatch):
    _stub_oauth(monkeypatch)
    auth = resolve_auth(host="https://h", token="static-tok", profile="fevm")
    assert auth.method == "oauth"
    assert auth.token_provider() == "oauth-tok"


def test_static_token_used_when_no_profile(monkeypatch):
    auth = resolve_auth(host="https://h", token="static-tok")
    assert auth.method == "static"
    assert auth.token_provider() == "static-tok"
    assert auth.host == "https://h"


def test_static_token_requires_host(monkeypatch):
    with pytest.raises(MissingCredential):
        resolve_auth(token="static-tok")  # no host


def test_bare_host_falls_back_to_oauth_default_chain(monkeypatch):
    _stub_oauth(monkeypatch)
    auth = resolve_auth(host="https://h")  # host but no token, no profile
    assert auth.method == "oauth"


def test_prefer_oauth_false_lets_static_win_over_profile(monkeypatch):
    _stub_oauth(monkeypatch)
    auth = resolve_auth(host="https://h", token="static-tok", profile="fevm", prefer_oauth=False)
    assert auth.method == "static"
    assert auth.token_provider() == "static-tok"


def test_nothing_set_raises_actionable_error(monkeypatch):
    with pytest.raises(MissingCredential) as exc:
        resolve_auth()
    assert "auth login" in str(exc.value)  # tells the user how to fix it


def test_env_is_read_when_args_absent(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://env-host")
    monkeypatch.setenv("DATABRICKS_TOKEN", "env-tok")
    auth = resolve_auth()
    assert auth.method == "static"
    assert auth.host == "https://env-host"
    assert auth.token_provider() == "env-tok"


def test_host_trailing_slash_is_stripped(monkeypatch):
    auth = resolve_auth(host="https://h/", token="t")
    assert auth.host == "https://h"


def test_databrickscfg_host_parsing(monkeypatch, tmp_path):
    cfg = tmp_path / ".databrickscfg"
    cfg.write_text(
        "[DEFAULT]\nhost = https://default-host\n\n"
        "[fevm]\nhost      = https://fevm-host\ntoken = ignored\n"
    )
    monkeypatch.setattr(databricks_auth.Path, "home", staticmethod(lambda: tmp_path))
    assert databricks_auth._databrickscfg_host("fevm") == "https://fevm-host"
    assert databricks_auth._databrickscfg_host("DEFAULT") == "https://default-host"
    assert databricks_auth._databrickscfg_host("nonexistent") is None


def test_oauth_resolves_host_from_profile_when_host_absent(monkeypatch, tmp_path):
    # No explicit host, but the profile has one in .databrickscfg — OAuth should find it and
    # then invoke the CLI token fetch (which we stub out).
    cfg = tmp_path / ".databrickscfg"
    cfg.write_text("[fevm]\nhost = https://fevm-host\n")
    monkeypatch.setattr(databricks_auth.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(
        databricks_auth,
        "_cli_oauth_token",
        lambda **_kw: "cli-oauth-tok",
    )
    auth = resolve_auth(profile="fevm")
    assert auth.method == "oauth"
    assert auth.host == "https://fevm-host"
    assert auth.token_provider() == "cli-oauth-tok"
