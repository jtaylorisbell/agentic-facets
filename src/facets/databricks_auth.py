"""Databricks authentication for the model provider.

The cookbook talks to a Databricks foundation model over the Unity AI Gateway, an
OpenAI-compatible surface that expects a bearer token in the ``Authorization`` header. There are
two legitimate ways to get that token, and this module resolves between them with an explicit
priority so the rule that matters is never violated:

1. **OAuth (preferred).** A user-to-machine OAuth flow set up with ``databricks auth login``. We
   read a fresh token from the Databricks CLI (``databricks auth token``), which serves it from
   the local cache and *refreshes* it when it is near expiry — so a long eval sweep does not die
   mid-run. Shelling out to the CLI (which external users install to log in anyway) keeps the
   cookbook's runtime dependency-lean: no extra SDK, no lockfile churn.
2. **Static bearer (fallback).** A ``DATABRICKS_TOKEN`` injected into the environment — the shape
   CI uses when a secret is mounted directly. Convenient, non-refreshing, and easy to leak, so it
   is a fallback, not the default.

Either way the model provider is handed a *token provider* — a zero-arg callable returning a
fresh bearer — rather than a frozen string, so the OAuth path can refresh transparently. The
resolution logic here is pure and unit-tested offline; the actual network handshake only happens
when the returned provider is first called.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from facets.config import load_env

TokenProvider = Callable[[], str]


@dataclass
class ResolvedAuth:
    """The host to call and a callable that returns a fresh bearer token for it."""

    host: str
    token_provider: TokenProvider
    #: "oauth" | "static" — how the token is obtained, for logging/diagnostics only.
    method: str


def resolve_auth(
    *,
    host: str | None = None,
    token: str | None = None,
    profile: str | None = None,
    prefer_oauth: bool = True,
) -> ResolvedAuth:
    """Resolve how to authenticate to the Databricks gateway.

    Priority (with ``prefer_oauth=True``, the default):

    1. If a **profile** is named (arg or ``DATABRICKS_CONFIG_PROFILE``), use OAuth via that
       profile — an explicit profile is an explicit "use OAuth" signal.
    2. Otherwise, if a **static token** is available (arg or ``DATABRICKS_TOKEN``), use it. This is
       the CI/injected-secret fallback.
    3. Otherwise, fall back to the SDK's ambient default auth chain (which itself prefers OAuth).

    Set ``prefer_oauth=False`` to swap 1 and 2 (static token wins even if a profile is set) — used
    only for tests. Raises :class:`~facets.config.MissingCredential` if nothing resolves.
    """
    load_env()
    host = host or os.environ.get("DATABRICKS_HOST")
    token = token or os.environ.get("DATABRICKS_TOKEN")
    profile = profile or os.environ.get("DATABRICKS_CONFIG_PROFILE")

    static_available = bool(token)
    profile_available = bool(profile)

    # Decide the order in which to try OAuth-via-profile vs. a static token.
    if prefer_oauth and profile_available:
        return _oauth_auth(host, profile)
    if static_available:
        if not host:
            _raise_missing("a static DATABRICKS_TOKEN was found but DATABRICKS_HOST is not set")
        return ResolvedAuth(host=host.rstrip("/"), token_provider=lambda: token, method="static")
    if profile_available or host:
        # Either an explicit profile, or a host we can hand to the SDK's default OAuth chain.
        return _oauth_auth(host, profile)
    _raise_missing("no DATABRICKS_CONFIG_PROFILE, DATABRICKS_TOKEN, or DATABRICKS_HOST is set")


def _oauth_auth(host: str | None, profile: str | None) -> ResolvedAuth:
    """Build an OAuth token provider backed by the Databricks CLI (``databricks auth token``).

    The CLI serves the U2M token from ``~/.databricks/token-cache.json`` and refreshes it when
    near expiry, so the returned provider yields a fresh bearer on every call. We need a host: it
    is the gateway base URL, and it also disambiguates the token cache when no profile is given.
    """
    resolved_host = _resolve_oauth_host(host, profile)
    login_hint = f" --profile {profile}" if profile else f" --host {resolved_host}"

    def _provider() -> str:
        return _cli_oauth_token(profile=profile, host=None if profile else resolved_host,
                                login_hint=login_hint)

    return ResolvedAuth(host=resolved_host.rstrip("/"), token_provider=_provider, method="oauth")


def _resolve_oauth_host(host: str | None, profile: str | None) -> str:
    """Determine the workspace host for OAuth: explicit host wins, else the profile's host."""
    if host:
        return host.rstrip("/")
    if profile:
        cfg_host = _databrickscfg_host(profile)
        if cfg_host:
            return cfg_host.rstrip("/")
    raise _missing("Could not determine the Databricks host for OAuth (set DATABRICKS_HOST).")


def _databrickscfg_host(profile: str) -> str | None:
    """Read a profile's ``host`` from ``~/.databrickscfg`` without a full INI dependency."""
    cfg = Path.home() / ".databrickscfg"
    if not cfg.is_file():
        return None
    in_section = False
    for raw in cfg.read_text().splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_section = line[1:-1] == profile
        elif in_section and line.lower().startswith("host") and "=" in line:
            return line.split("=", 1)[1].strip()
    return None


def _cli_oauth_token(*, profile: str | None, host: str | None, login_hint: str) -> str:
    """Shell out to ``databricks auth token`` and return the bearer (refreshed by the CLI)."""
    import json
    import shutil
    import subprocess

    cli = shutil.which("databricks")
    if cli is None:
        raise _missing(
            "OAuth needs the Databricks CLI on PATH (https://docs.databricks.com/dev-tools/cli). "
            "Or set a static DATABRICKS_TOKEN for CI."
        )
    cmd = [cli, "auth", "token", "-o", "json"]
    if profile:
        cmd += ["-p", profile]
    if host:
        cmd += ["--host", host]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True)
    except subprocess.CalledProcessError as exc:
        raise _missing(
            f"`databricks auth token` failed ({exc.stderr.strip() or 'unknown error'}). "
            f"Log in first: `databricks auth login{login_hint}`."
        ) from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _missing(f"Could not run the Databricks CLI for OAuth: {exc}") from exc

    try:
        token = json.loads(out.stdout)["access_token"]
    except (ValueError, KeyError) as exc:
        raise _missing("Databricks CLI returned no access_token for OAuth.") from exc
    if not token:
        raise _missing(
            f"Databricks OAuth token was empty. Run `databricks auth login{login_hint}`."
        )
    return token


def _missing(detail: str):
    from facets.config import MissingCredential

    return MissingCredential(
        f"{detail}\n"
        "How to fix (preferred, OAuth): `databricks auth login --host <workspace-url> "
        "--profile <name>`, then set DATABRICKS_CONFIG_PROFILE=<name> (and DATABRICKS_HOST).\n"
        "Or, for CI, set DATABRICKS_HOST and a DATABRICKS_TOKEN secret."
    )


def _raise_missing(detail: str):
    raise _missing(detail)
