"""The FACETS manifest: a machine-readable classification of a system.

Every runnable recipe ships a ``facets.yaml`` describing its architecture across the six axes.
This module loads that file, validates it against ``schema/facets.schema.json``, and exposes it
as a typed :class:`FacetsManifest`. The manifest is what makes FACETS *adoptable* — the goal is
for external repos to publish their own ``facets.yaml`` and say "here is our FACETS profile."
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

# schema/facets.schema.json lives at the repo root, three parents up from this file
# (src/facets/manifest.py -> src/facets -> src -> repo root).
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "facets.schema.json"


class Feedback(BaseModel):
    mode: str
    mechanisms: list[str] = Field(default_factory=list)


class Authority(BaseModel):
    level: str
    allowed_actions: list[str] = Field(default_factory=list)


class Control(BaseModel):
    mode: str
    boundaries: dict[str, Any] = Field(default_factory=dict)


class Execution(BaseModel):
    pattern: str


class Topology(BaseModel):
    pattern: str


class State(BaseModel):
    durability: str
    memory: str | None = None
    source_of_truth: str | None = None


class FacetsManifest(BaseModel):
    """The typed form of a ``facets.yaml``."""

    name: str
    description: str = ""
    feedback: Feedback
    authority: Authority
    control: Control
    execution: Execution
    topology: Topology
    state: State

    def summary_line(self) -> str:
        """One-line FACETS profile, e.g. for a docs badge or a log."""
        return (
            f"F={self.feedback.mode} "
            f"A={self.authority.level} "
            f"C={self.control.mode} "
            f"E={self.execution.pattern} "
            f"T={self.topology.pattern} "
            f"S={self.state.durability}"
        )


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text())


def validate_manifest(data: dict[str, Any]) -> None:
    """Raise ``jsonschema.ValidationError`` if ``data`` does not conform to the schema."""
    import jsonschema

    jsonschema.validate(instance=data, schema=_schema())


def load_manifest(path: str | Path, *, validate: bool = True) -> FacetsManifest:
    """Load and (by default) schema-validate a ``facets.yaml`` into a :class:`FacetsManifest`."""
    raw = yaml.safe_load(Path(path).read_text())
    if validate:
        validate_manifest(raw)
    return FacetsManifest.model_validate(raw)
