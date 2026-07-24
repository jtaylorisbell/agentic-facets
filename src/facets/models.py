"""Model providers: the *decision capability* of an agent.

This is the seam that keeps the cookbook framework-neutral. Every provider returns the same
:class:`ModelResponse` — either a final answer or a batch of tool calls — so the
:class:`~facets.agents.Agent` loop is identical whether it is driven by a scripted
:class:`FakeModel` (offline, deterministic, the backbone of the tests) or by a real
:class:`DatabricksModel` talking to a Databricks foundation-model endpoint.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from facets.messages import Message, Role, ToolCall

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from facets.tools import ToolSpec


@dataclass
class Usage:
    """Accounting carried on every response so traces can roll up cost."""

    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 1

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.model_calls + other.model_calls,
        )


@dataclass
class ModelResponse:
    """A single model turn.

    Exactly one of ``text`` / ``tool_calls`` is the operative field: if ``tool_calls`` is
    non-empty the agent should execute them, otherwise ``text`` is the final answer.
    """

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)

    @property
    def is_final(self) -> bool:
        return not self.tool_calls


@runtime_checkable
class ModelProvider(Protocol):
    """The one method every backend implements."""

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None = None,
        **options: Any,
    ) -> ModelResponse: ...


# --------------------------------------------------------------------------------------------
# FakeModel — deterministic, offline, scriptable.
# --------------------------------------------------------------------------------------------


def call(name: str, **arguments: Any) -> ToolCall:
    """Terse helper for building a scripted tool call in tests and recipe demos."""
    return ToolCall(id=f"call_{name}", name=name, arguments=arguments)


def _rough_token_count(text: str) -> int:
    """A stable, dependency-free token estimate (~4 chars/token) for offline accounting."""
    return max(1, len(text) // 4)


class FakeModel:
    """A model whose behaviour is fully specified up front.

    Two modes:

    * **scripted** — pass a list of :class:`ModelResponse` (or the shorthand: a ``list`` of
      :class:`~facets.messages.ToolCall` for a tool step, or a ``str`` for a final answer).
      Each ``complete`` call returns the next entry.
    * **policy** — pass a callable ``(messages, tools) -> ModelResponse`` for behaviour that
      depends on the conversation (used to demonstrate recovery from a bad tool result).

    When the script is exhausted it falls back to a final answer (``exhausted_answer``), which
    keeps a mis-specified demo from hanging.
    """

    def __init__(
        self,
        script: Sequence[ModelResponse | list[ToolCall] | str] | None = None,
        *,
        policy: Callable[[Sequence[Message], Sequence[ToolSpec] | None], ModelResponse]
        | None = None,
        exhausted_answer: str = "No further steps.",
    ):
        if (script is None) == (policy is None):
            raise ValueError("Provide exactly one of `script` or `policy`.")
        self._script: list[ModelResponse] = [_coerce(s) for s in (script or [])]
        self._policy = policy
        self._exhausted_answer = exhausted_answer
        self._cursor = 0

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None = None,
        **options: Any,
    ) -> ModelResponse:
        if self._policy is not None:
            resp = self._policy(messages, tools)
        elif self._cursor < len(self._script):
            resp = self._script[self._cursor]
            self._cursor += 1
        else:
            resp = ModelResponse(text=self._exhausted_answer)

        # Attach a deterministic usage estimate if the script did not specify one.
        if resp.usage.input_tokens == 0 and resp.usage.output_tokens == 0:
            prompt = " ".join(m.content or "" for m in messages)
            out = resp.text or " ".join(c.pretty() for c in resp.tool_calls)
            resp.usage = Usage(
                input_tokens=_rough_token_count(prompt),
                output_tokens=_rough_token_count(out),
                model_calls=1,
            )
        return resp


def _coerce(entry: ModelResponse | list[ToolCall] | str) -> ModelResponse:
    if isinstance(entry, ModelResponse):
        return entry
    if isinstance(entry, str):
        return ModelResponse(text=entry)
    return ModelResponse(tool_calls=list(entry))


# --------------------------------------------------------------------------------------------
# DatabricksModel — real model via the Unity AI Gateway (OpenAI-compatible surface).
# --------------------------------------------------------------------------------------------


class DatabricksModel:
    """Talks to a Databricks model through the Unity AI Gateway.

    The gateway exposes an OpenAI-compatible API, so this is a thin adapter over the ``openai``
    async client pointed at ``{host}/ai-gateway/mlflow/v1``. The ``model`` is a Unity Catalog
    model-service name (e.g. ``system.ai.claude-sonnet-5`` or ``system.ai.gpt-5``).

    Credentials are read from the environment by default:

    * ``DATABRICKS_HOST``  — workspace URL, e.g. ``https://<workspace>.cloud.databricks.com``
    * ``DATABRICKS_TOKEN`` — a Databricks token authorized for the gateway
    * ``FACETS_MODEL``     — the model-service name (overridable via ``model=``)
    """

    #: The Unity AI Gateway path appended to the workspace host.
    GATEWAY_PATH = "/ai-gateway/mlflow/v1"

    def __init__(
        self,
        model: str | None = None,
        *,
        host: str | None = None,
        token: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = 2048,
    ):
        host = host or os.environ.get("DATABRICKS_HOST")
        token = token or os.environ.get("DATABRICKS_TOKEN")
        self.model = model or os.environ.get("FACETS_MODEL", "system.ai.claude-sonnet-5")
        # temperature is opt-in: several gateway models (e.g. Anthropic) reject it outright, so
        # we only send it when a caller explicitly asks for one.
        self.temperature = temperature
        self.max_tokens = max_tokens
        if not host or not token:
            raise RuntimeError(
                "DatabricksModel needs DATABRICKS_HOST and DATABRICKS_TOKEN "
                "(set them in the environment or pass host=/token=)."
            )
        # Imported lazily so the offline path never requires the openai package to be wired up.
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=token,
            base_url=f"{host.rstrip('/')}{self.GATEWAY_PATH}",
        )

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None = None,
        **options: Any,
    ) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [_to_openai_message(m) for m in messages],
        }
        temperature = options.get("temperature", self.temperature)
        if temperature is not None:
            payload["temperature"] = temperature
        max_tokens = options.get("max_tokens", self.max_tokens)
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = [t.to_openai() for t in tools]
            payload["tool_choice"] = options.get("tool_choice", "auto")

        completion = await self._create_with_fallback(payload)
        choice = completion.choices[0].message
        tool_calls = [
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=json.loads(tc.function.arguments or "{}"),
            )
            for tc in (choice.tool_calls or [])
        ]
        usage = Usage(
            input_tokens=getattr(completion.usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(completion.usage, "completion_tokens", 0) or 0,
            model_calls=1,
        )
        return ModelResponse(text=choice.content, tool_calls=tool_calls, usage=usage)

    async def _create_with_fallback(self, payload: dict[str, Any]) -> Any:
        """Call the gateway, dropping any parameter it explicitly rejects, then retrying.

        Gateway model families disagree on which optional parameters they accept — Anthropic
        models, for example, reject ``temperature``. Rather than hard-code a per-model matrix,
        we optimistically send the parameters and strip whichever one the API names in a
        ``does not support the X parameter`` error. Bounded to the optional keys so a genuine
        request error still surfaces.
        """
        from openai import BadRequestError

        removable = ["temperature", "max_tokens", "tool_choice"]
        for _ in range(len(removable) + 1):
            try:
                return await self._client.chat.completions.create(**payload)
            except BadRequestError as exc:
                message = str(exc)
                dropped = next(
                    (k for k in removable if k in payload and f"the {k} parameter" in message),
                    None,
                )
                if dropped is None:
                    raise
                payload.pop(dropped, None)
        # Should be unreachable: the loop above either returns or raises.
        return await self._client.chat.completions.create(**payload)


def _to_openai_message(m: Message) -> dict[str, Any]:
    """Translate a FACETS :class:`Message` into an OpenAI/Databricks chat message."""
    if m.role is Role.TOOL and m.tool_result is not None:
        return {
            "role": "tool",
            "tool_call_id": m.tool_result.tool_call_id,
            "content": m.tool_result.as_text(),
        }
    if m.role is Role.ASSISTANT and m.tool_calls:
        return {
            "role": "assistant",
            "content": m.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in m.tool_calls
            ],
        }
    return {"role": m.role.value, "content": m.content or ""}
