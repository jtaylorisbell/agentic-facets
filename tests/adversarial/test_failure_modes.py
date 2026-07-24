"""Adversarial tests — the "failure lab" the recipes reference.

These deliberately break the agent to prove the control boundaries hold:
  * an infinite loop is cut off by max_steps (not left to burn tokens forever),
  * a hallucinated tool name degrades to a soft error the model can recover from,
  * an over-tight step budget produces a truncated (failing) result, not a crash,
  * an unauthorized action is denied by the approval policy, not the prompt.
"""

from __future__ import annotations

from facets.agents import Agent, Budget, ExecutionContext
from facets.approvals import ApprovalPolicy, AuthorityLevel, Decision
from facets.models import FakeModel, ModelResponse, call
from facets.tools import tool


@tool
async def query_logs(pipeline: str) -> str:
    """Return logs."""
    return "ERROR: schema mismatch on 'amount'"


# ---- Infinite loop is bounded by max_steps ------------------------------------------------


def _always_calls_tool(messages, tools):
    return ModelResponse(tool_calls=[call("query_logs", pipeline="orders_daily")])


async def test_infinite_loop_is_cut_off():
    agent = Agent(
        "looper", FakeModel(policy=_always_calls_tool), [query_logs], budget=Budget(max_steps=5)
    )
    result = await agent.run("investigate")
    assert result.stopped_reason == "max_steps"
    assert result.steps == 5
    assert result.hit_limit


# ---- Tool hallucination is a soft error the model can recover from ------------------------


async def test_wrong_tool_then_recovery():
    model = FakeModel(
        script=[
            [call("fetch_the_logs", pipeline="orders_daily")],  # not a real tool
            [call("query_logs", pipeline="orders_daily")],  # correct tool
            "Recovered: the root cause is a schema mismatch on 'amount'.",
        ]
    )
    agent = Agent("investigator", model, [query_logs])
    result = await agent.run("investigate")

    assert result.stopped_reason == "final"
    assert "schema mismatch" in result.answer
    # Only the real tool shows up in the trace; the hallucinated one produced a soft error.
    assert result.trace.tool_calls == ["query_logs"]
    # The soft error message named the available tools so the model could correct itself.
    tool_messages = [m for m in result.messages if m.role.value == "tool"]
    assert any(m.tool_result.is_error for m in tool_messages)
    assert any("query_logs" in (m.content or "") for m in tool_messages if m.tool_result.is_error)


# ---- Over-tight budget truncates rather than crashing -------------------------------------


async def test_too_tight_budget_truncates():
    model = FakeModel(
        script=[[call("query_logs", pipeline="orders_daily")], "Answer after evidence."]
    )
    # max_steps=1: the agent uses its single step to call the tool, then is cut off before it
    # can produce the final answer.
    agent = Agent("hasty", model, [query_logs], budget=Budget(max_steps=1))
    result = await agent.run("investigate")
    assert result.stopped_reason == "max_steps"
    assert result.steps == 1


# ---- Authority: an unauthorized action is denied outside the model ------------------------


async def test_approval_policy_blocks_unauthorized_action():
    from tools import roll_back_deployment

    # Advisory authority => no action may execute, regardless of what the agent "wants".
    policy = ApprovalPolicy(level=AuthorityLevel.ADVISORY)
    ctx = ExecutionContext(task_id="t", approvals=policy)
    result = await roll_back_deployment.execute({"deployment_id": "deploy-8842"}, ctx)
    assert result.content["executed"] is False
    assert result.content["decision"] == Decision.DENY.value
