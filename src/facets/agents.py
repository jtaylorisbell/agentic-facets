"""The Agent: a model-directed tool loop, plus the plumbing every recipe shares.

This module is the heart of the **Control** axis. A :class:`~facets.tools.Tool` decides
nothing about *what happens next*; a code-directed workflow decides everything up front; an
:class:`Agent` hands that decision to the model on every turn:

    Observe → Decide → Act → Observe result → Decide again → … → Finish

The loop is bounded by ``max_steps`` (a Control boundary — the difference between a *bounded*
tool-using agent and an *open-ended* one) so a confused model degrades into a truncated answer
rather than an infinite spend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from facets.messages import Message, ToolResult
from facets.models import Usage
from facets.tools import Tool, ToolRegistry, ToolSpec
from facets.tracing import Trace

if TYPE_CHECKING:
    from facets.approvals import ApprovalPolicy
    from facets.models import ModelProvider
    from facets.state import StateStore, TaskState


@dataclass
class Budget:
    """Control boundaries. ``max_steps`` bounds the loop; ``max_tokens`` is advisory (checked
    between steps) so a runaway conversation stops accruing cost."""

    max_steps: int = 8
    max_tokens: int | None = None


@dataclass
class ExecutionContext:
    """Everything a tool or nested agent needs at runtime.

    Threaded through the whole call tree so tools can read/write task state, request approvals,
    and contribute to a single shared trace.
    """

    task_id: str
    trace: Trace = field(default_factory=Trace)
    budget: Budget = field(default_factory=Budget)
    state: TaskState | None = None
    store: StateStore | None = None
    approvals: ApprovalPolicy | None = None
    scratch: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """The structured outcome of an agent run."""

    answer: str
    steps: int
    usage: Usage
    trace: Trace
    stopped_reason: str  # "final" | "max_steps" | "max_tokens"
    messages: list[Message] = field(default_factory=list)

    @property
    def hit_limit(self) -> bool:
        return self.stopped_reason != "final"


class Agent:
    """A single model-directed decision context with a set of tools.

    Per the framework's design principle, *this should usually be the default* — reach for
    multiple agents only when one context genuinely cannot hold the problem.
    """

    def __init__(
        self,
        name: str,
        model: ModelProvider,
        tools: ToolRegistry | list[Tool] | None = None,
        *,
        system_prompt: str = "",
        budget: Budget | None = None,
    ):
        self.name = name
        self.model = model
        if isinstance(tools, ToolRegistry):
            self.tools = tools
        else:
            self.tools = ToolRegistry(tools or [])
        self.system_prompt = system_prompt
        self.budget = budget or Budget()

    async def run(self, goal: str, context: ExecutionContext | None = None) -> AgentResult:
        ctx = context or ExecutionContext(task_id=f"{self.name}-task")
        trace = ctx.trace
        specs: list[ToolSpec] = self.tools.specs()

        messages: list[Message] = []
        if self.system_prompt:
            messages.append(Message.system(self.system_prompt))
        messages.append(Message.user(goal))

        total = Usage(model_calls=0)
        steps = 0
        stopped_reason = "final"
        answer = ""

        while True:
            if steps >= self.budget.max_steps:
                stopped_reason = "max_steps"
                answer = _truncated_answer(messages)
                break
            if self.budget.max_tokens is not None and total.input_tokens + total.output_tokens > (
                self.budget.max_tokens
            ):
                stopped_reason = "max_tokens"
                answer = _truncated_answer(messages)
                break

            steps += 1
            with trace.span(f"{self.name}:decide", "model", agent=self.name, step=steps):
                response = await self.model.complete(messages, specs or None)
            total = total + response.usage
            trace.record_usage(response.usage)

            if response.is_final:
                answer = response.text or ""
                messages.append(Message.assistant(content=answer))
                stopped_reason = "final"
                break

            # The model chose to act: record the assistant turn, run each tool, feed results back.
            messages.append(
                Message.assistant(content=response.text, tool_calls=response.tool_calls)
            )
            for tc in response.tool_calls:
                args = {**tc.arguments, "__call_id__": tc.id}
                result = await self._invoke_tool(tc.name, args, ctx)
                messages.append(Message.tool(result))

        return AgentResult(
            answer=answer,
            steps=steps,
            usage=total,
            trace=trace,
            stopped_reason=stopped_reason,
            messages=messages,
        )

    async def _invoke_tool(
        self, name: str, arguments: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        tool = self.tools.get(name)
        if tool is None:
            # Tool hallucination — return a soft error so the model can pick a real tool.
            return ToolResult(
                tool_call_id=arguments.get("__call_id__", name),
                name=name,
                content=(
                    f"Unknown tool '{name}'. Available tools: {', '.join(self.tools.names())}."
                ),
                is_error=True,
            )
        with ctx.trace.span(f"{self.name}:{name}", "tool", tool=name, agent=self.name):
            return await tool.execute(arguments, ctx)


def _truncated_answer(messages: list[Message]) -> str:
    """Best-effort answer when the loop is cut short — the last thing the model said, if any."""
    for m in reversed(messages):
        if m.content:
            return m.content
    return "Stopped before producing a final answer."


class _AgentTool:
    """Adapts an :class:`Agent` so it can be called *as a tool* by a manager agent.

    This is the mechanism behind the **manager–worker** topology (recipe 05): workers are
    intelligent tools. The manager stays responsible; a worker runs in its own isolated
    context and returns a result — it does not take over the conversation (that would be a
    *handoff*, recipe 06).
    """

    def __init__(self, agent: Agent, *, name: str | None = None, description: str | None = None):
        self._agent = agent
        tool_name = name or f"delegate_to_{agent.name}"
        tool_desc = description or f"Delegate a subtask to the {agent.name} specialist agent."
        self._spec = ToolSpec(
            name=tool_name,
            description=tool_desc,
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "A self-contained instruction for the specialist.",
                    }
                },
                "required": ["task"],
            },
        )

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        call_id = arguments.get("__call_id__", self._spec.name)
        task = arguments.get("task", "")
        # The worker shares the trace (so its cost rolls up) but gets a fresh message context.
        with context.trace.span(f"agent:{self._agent.name}", "agent", agent=self._agent.name):
            sub = await self._agent.run(task, context)
        return ToolResult(tool_call_id=call_id, name=self._spec.name, content=sub.answer)


def agent_as_tool(
    agent: Agent, *, name: str | None = None, description: str | None = None
) -> Tool:
    """Wrap an agent so a manager can delegate to it. See :class:`_AgentTool`."""
    return _AgentTool(agent, name=name, description=description)
