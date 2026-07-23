"""Unit tests for scorers and the Evaluator report shape."""

from facets.agents import Agent, Budget
from facets.evaluation import (
    EvalCase,
    Evaluator,
    task_success_scorer,
    tool_correctness_scorer,
)
from facets.models import FakeModel, ModelResponse, call
from facets.tools import tool


@tool
async def query_logs(pipeline: str) -> str:
    """Logs."""
    return "schema mismatch"


def _case():
    return EvalCase(
        id="orders-fail",
        goal="investigate",
        expected_root_cause="schema mismatch",
        expected_tools=["query_logs"],
    )


async def _run_success():
    model = FakeModel(script=[[call("query_logs", pipeline="p")], "It was a schema mismatch."])
    agent = Agent("a", model, [query_logs])
    return await agent.run("investigate")


async def test_task_success_and_tool_correctness_perfect():
    result = await _run_success()
    case = _case()
    assert task_success_scorer()(case, result).value == 1.0
    assert tool_correctness_scorer()(case, result).value == 1.0


async def test_task_success_zero_when_root_cause_missing():
    model = FakeModel(script=["I could not determine the cause."])
    agent = Agent("a", model, [query_logs])
    result = await agent.run("investigate")
    assert task_success_scorer()(_case(), result).value == 0.0


def _never_finishes(messages, tools):
    return ModelResponse(tool_calls=[call("query_logs", pipeline="p")])


async def test_task_success_zero_when_truncated():
    model = FakeModel(policy=_never_finishes)
    agent = Agent("a", model, [query_logs], budget=Budget(max_steps=2))
    result = await agent.run("loop")
    score = task_success_scorer()(_case(), result)
    assert score.value == 0.0
    assert "max_steps" in score.detail


async def test_tool_correctness_partial():
    result = await _run_success()
    case = EvalCase(id="c", goal="g", expected_tools=["query_logs", "query_metrics"])
    assert tool_correctness_scorer()(case, result).value == 0.5


async def test_evaluator_report_row():
    result = await _run_success()
    report = Evaluator().evaluate(_case(), recipe="01_single_tool_agent", result=result)
    row = report.as_row()
    assert row["recipe"] == "01_single_tool_agent"
    assert row["task_success"] == 1.0
    assert row["model_calls"] == 2
    assert "total_tokens" in row
