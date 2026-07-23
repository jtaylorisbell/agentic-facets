"""Unit tests for the Agent loop: tool execution, finishing, limits, delegation."""

from facets.agents import Agent, Budget, ExecutionContext, agent_as_tool
from facets.models import FakeModel, ModelResponse, call
from facets.tools import tool


@tool
async def query_logs(pipeline: str) -> str:
    """Return recent logs for a pipeline."""
    return f"ERROR in {pipeline}: schema mismatch on column 'amount'"


async def test_agent_runs_tool_then_finishes():
    model = FakeModel(
        script=[
            [call("query_logs", pipeline="orders")],
            "Root cause: schema mismatch on column 'amount'.",
        ]
    )
    agent = Agent("investigator", model, [query_logs])
    result = await agent.run("Investigate the orders pipeline failure.")

    assert result.stopped_reason == "final"
    assert "schema mismatch" in result.answer
    assert result.steps == 2
    assert result.trace.tool_calls == ["query_logs"]
    assert result.usage.model_calls == 2


def _never_finishes(messages, tools):
    """A policy that always asks for another tool call — never returns a final answer."""
    return ModelResponse(tool_calls=[call("query_logs", pipeline="p")])


async def test_agent_stops_at_max_steps():
    model = FakeModel(policy=_never_finishes)
    agent = Agent("looper", model, [query_logs], budget=Budget(max_steps=3))
    result = await agent.run("loop forever")
    assert result.stopped_reason == "max_steps"
    assert result.steps == 3


async def test_unknown_tool_is_soft_error_then_recover():
    model = FakeModel(
        script=[
            [call("nonexistent_tool", foo="bar")],
            [call("query_logs", pipeline="orders")],
            "Recovered and found the schema mismatch.",
        ]
    )
    agent = Agent("investigator", model, [query_logs])
    result = await agent.run("investigate")
    assert result.stopped_reason == "final"
    assert "Recovered" in result.answer
    # The bad call is not traced as a real tool; the good one is.
    assert result.trace.tool_calls == ["query_logs"]


async def test_agent_as_tool_delegation_shares_trace():
    worker_model = FakeModel(
        script=[[call("query_logs", pipeline="orders")], "logs show a schema mismatch"]
    )
    worker = Agent("log_worker", worker_model, [query_logs])
    worker_tool = agent_as_tool(worker, name="ask_log_worker")

    manager_model = FakeModel(
        script=[
            [call("ask_log_worker", task="check the logs")],
            "Manager synthesis: schema mismatch confirmed by log worker.",
        ]
    )
    manager = Agent("manager", manager_model, [worker_tool])

    ctx = ExecutionContext(task_id="incident-1")
    result = await manager.run("Delegate and synthesize.", ctx)

    assert result.stopped_reason == "final"
    assert "schema mismatch confirmed" in result.answer
    # Worker's model call rolls up into the shared trace (manager 2 + worker 2 = 4).
    assert result.trace.model_calls == 4
    # The nested agent span is recorded.
    assert any(s.kind == "agent" for s in result.trace.spans)
