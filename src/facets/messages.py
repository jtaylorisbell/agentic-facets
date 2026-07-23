"""Conversation primitives shared by every recipe.

These types are deliberately provider-neutral. The :class:`~facets.models.ModelProvider`
implementations translate to and from whatever wire format their backend uses, so the
:class:`~facets.agents.Agent` loop only ever sees these shapes.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Role(StrEnum):
    """Who authored a message."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """A model's request to invoke a tool.

    ``id`` correlates the call with its :class:`ToolResult` on the way back, mirroring the
    OpenAI ``tool_calls`` / ``tool_call_id`` convention so the Databricks adapter is a thin
    translation layer.
    """

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    def pretty(self) -> str:
        return f"{self.name}({json.dumps(self.arguments, sort_keys=True)})"


class ToolResult(BaseModel):
    """The outcome of executing a :class:`ToolCall`."""

    tool_call_id: str
    name: str
    content: Any
    is_error: bool = False

    def as_text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return json.dumps(self.content, default=str, sort_keys=True)


class Message(BaseModel):
    """A single turn in the conversation.

    An assistant turn may carry ``tool_calls``; a tool turn carries a single ``tool_result``.
    """

    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_result: ToolResult | None = None

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role=Role.USER, content=content)

    @classmethod
    def assistant(
        cls, content: str | None = None, tool_calls: list[ToolCall] | None = None
    ) -> Message:
        return cls(role=Role.ASSISTANT, content=content, tool_calls=tool_calls or [])

    @classmethod
    def tool(cls, result: ToolResult) -> Message:
        return cls(role=Role.TOOL, content=result.as_text(), tool_result=result)
