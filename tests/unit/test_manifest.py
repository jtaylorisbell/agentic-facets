"""Unit tests for facets.yaml loading + JSON-schema validation."""

import textwrap

import jsonschema
import pytest

from facets.manifest import load_manifest, validate_manifest

VALID = {
    "name": "bounded-incident-investigator",
    "description": "A single tool-using agent.",
    "feedback": {"mode": "closed-loop", "mechanisms": ["environmental-verification"]},
    "authority": {"level": "advisory", "allowed_actions": []},
    "control": {"mode": "model-directed", "boundaries": {"max_steps": 8}},
    "execution": {"pattern": "planner-executor"},
    "topology": {"pattern": "single-agent"},
    "state": {"durability": "request-local", "memory": "context-only"},
}


def test_valid_manifest_passes_schema():
    validate_manifest(VALID)  # should not raise


def test_invalid_enum_rejected():
    bad = {**VALID, "control": {"mode": "vibes-directed"}}
    with pytest.raises(jsonschema.ValidationError):
        validate_manifest(bad)


def test_missing_required_axis_rejected():
    bad = {k: v for k, v in VALID.items() if k != "state"}
    with pytest.raises(jsonschema.ValidationError):
        validate_manifest(bad)


def test_load_manifest_from_yaml(tmp_path):
    path = tmp_path / "facets.yaml"
    path.write_text(
        textwrap.dedent(
            """
            name: demo
            feedback:
              mode: open-loop
            authority:
              level: advisory
            control:
              mode: code-directed
            execution:
              pattern: sequential
            topology:
              pattern: none
            state:
              durability: request-local
            """
        )
    )
    manifest = load_manifest(path)
    assert manifest.name == "demo"
    assert manifest.control.mode == "code-directed"
    assert manifest.summary_line().startswith("F=open-loop")


def test_repo_schema_is_wellformed():
    # The bundled schema must itself be a valid draft-07 schema.
    from facets.manifest import _schema

    jsonschema.Draft7Validator.check_schema(_schema())
