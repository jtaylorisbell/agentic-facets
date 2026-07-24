"""Tools: the *action capability* of an agent.

A :class:`Tool` is anything with a name, a description, a JSON-schema parameter spec, and an
async ``execute``. The :func:`tool` decorator builds one from a typed async function by
introspecting its signature, so recipe authors write plain functions.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Protocol, get_args, get_origin, runtime_checkable

from facets.messages import ToolResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from facets.agents import ExecutionContext


# JSON-schema fragment for the primitive Python types we support in tool signatures.
_PRIMITIVE_SCHEMA: dict[type, dict[str, str]] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    dict: {"type": "object"},
    list: {"type": "array"},
}


class ToolSpec:
    """A tool's public contract — the part a model sees when choosing what to call."""

    def __init__(self, name: str, description: str, parameters: dict[str, Any]):
        self.name = name
        self.description = description
        self.parameters = parameters

    def to_openai(self) -> dict[str, Any]:
        """Render as an OpenAI/Databricks ``tools`` entry."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@runtime_checkable
class Tool(Protocol):
    """The action interface. Implementations may be functions, agents, or classes."""

    @property
    def spec(self) -> ToolSpec: ...

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult: ...


def _type_to_schema(annotation: Any) -> dict[str, Any]:
    """Map a Python annotation to a JSON-schema fragment (best-effort, primitives + lists)."""
    origin = get_origin(annotation)
    if origin in (list, list):
        (item,) = get_args(annotation) or (str,)
        return {"type": "array", "items": _type_to_schema(item)}
    if annotation in _PRIMITIVE_SCHEMA:
        return dict(_PRIMITIVE_SCHEMA[annotation])
    # Unknown / complex types degrade to a permissive object.
    return {"type": "string"}


class _FunctionTool:
    """Wraps a plain async function as a :class:`Tool`."""

    def __init__(self, fn: Callable[..., Any], name: str, description: str):
        self._fn = fn
        self._spec = ToolSpec(name, description, _build_parameters(fn))

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        call_id = arguments.pop("__call_id__", self._spec.name)
        try:
            kwargs = _coerce_arguments(self._fn, dict(arguments))
            if _wants_context(self._fn):
                kwargs["context"] = context
            result = self._fn(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            return ToolResult(tool_call_id=call_id, name=self._spec.name, content=result)
        except Exception as exc:  # tools should fail soft — the agent can react and recover
            return ToolResult(
                tool_call_id=call_id,
                name=self._spec.name,
                content=f"{type(exc).__name__}: {exc}",
                is_error=True,
            )


def _wants_context(fn: Callable[..., Any]) -> bool:
    return "context" in inspect.signature(fn).parameters


def _coerce_arguments(fn: Callable[..., Any], arguments: dict[str, Any]) -> dict[str, Any]:
    """Coerce tool arguments to their annotated types.

    Models calling tools through the OpenAI-compatible surface sometimes send numbers as strings
    (``"start_line": "128"``) or booleans as strings. Rather than make every tool defensive, we
    coerce here, against the function's own annotations. Coercion is best-effort: if a value
    cannot be converted it is passed through unchanged so the tool can decide what to do.
    """
    sig = inspect.signature(fn)
    coerced = dict(arguments)
    for pname, param in sig.parameters.items():
        if pname not in coerced:
            continue
        annotation = param.annotation
        value = coerced[pname]
        if annotation is int and isinstance(value, (str, float)):
            try:
                # Accept "128" and "128.0"/128.0 alike (models are inconsistent here).
                coerced[pname] = int(float(value))
            except (ValueError, TypeError):
                pass
        elif annotation is float and isinstance(value, (str, int)):
            try:
                coerced[pname] = float(value)
            except (ValueError, TypeError):
                pass
        elif annotation is bool and isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "false"):
                coerced[pname] = lowered == "true"
    return coerced


def _build_parameters(fn: Callable[..., Any]) -> dict[str, Any]:
    """Introspect a function signature into a JSON-schema ``object``."""
    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname in ("context", "self"):
            continue
        annotation = param.annotation if param.annotation is not inspect.Parameter.empty else str
        properties[pname] = _type_to_schema(annotation)
        if param.default is inspect.Parameter.empty:
            required.append(pname)
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def tool(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Any:
    """Decorator turning a typed async function into a :class:`Tool`.

    The description defaults to the function's docstring; parameters are inferred from the
    signature. Add a ``context`` parameter to receive the :class:`ExecutionContext`.
    """

    def wrap(inner: Callable[..., Any]) -> _FunctionTool:
        tool_name = name or inner.__name__
        tool_desc = description or (inspect.getdoc(inner) or "").strip()
        return _FunctionTool(inner, tool_name, tool_desc)

    return wrap if fn is None else wrap(fn)


class ToolRegistry:
    """An ordered, name-addressable collection of tools available to an agent."""

    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self.add(t)

    def add(self, t: Tool) -> None:
        self._tools[t.spec.name] = t

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def openai_tools(self) -> list[dict[str, Any]]:
        return [s.to_openai() for s in self.specs()]

    def names(self) -> list[str]:
        return list(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools
