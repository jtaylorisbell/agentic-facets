"""Unit tests for the model layer: FakeModel scripting/policy, usage accounting."""

import pytest

from facets.messages import Message
from facets.models import FakeModel, ModelResponse, Usage, call


async def test_scripted_sequence_advances():
    model = FakeModel(script=[[call("query_logs", pipeline="p1")], "final answer"])
    r1 = await model.complete([Message.user("go")])
    assert not r1.is_final
    assert r1.tool_calls[0].name == "query_logs"

    r2 = await model.complete([Message.user("go")])
    assert r2.is_final
    assert r2.text == "final answer"


async def test_script_exhaustion_falls_back():
    model = FakeModel(script=["only answer"], exhausted_answer="done")
    await model.complete([Message.user("x")])
    tail = await model.complete([Message.user("x")])
    assert tail.is_final and tail.text == "done"


async def test_usage_estimated_when_unspecified():
    model = FakeModel(script=["hello world this is a longer answer"])
    r = await model.complete([Message.user("a reasonably long prompt here")])
    assert r.usage.input_tokens > 0
    assert r.usage.output_tokens > 0
    assert r.usage.model_calls == 1


async def test_explicit_usage_preserved():
    resp = ModelResponse(text="hi", usage=Usage(input_tokens=100, output_tokens=5))
    model = FakeModel(script=[resp])
    r = await model.complete([Message.user("x")])
    assert r.usage.input_tokens == 100
    assert r.usage.output_tokens == 5


async def test_policy_mode_reacts_to_conversation():
    from facets.messages import ToolResult

    def policy(messages, tools):
        # Finish once a tool result is present, otherwise call a tool.
        if any(m.role.value == "tool" for m in messages):
            return ModelResponse(text="resolved")
        return ModelResponse(tool_calls=[call("check")])

    model = FakeModel(policy=policy)
    first = await model.complete([Message.user("investigate")])
    assert not first.is_final

    tool_msg = Message.tool(ToolResult(tool_call_id="c", name="check", content="ok"))
    second = await model.complete([Message.user("investigate"), tool_msg])
    assert second.is_final and second.text == "resolved"


def test_requires_exactly_one_mode():
    with pytest.raises(ValueError):
        FakeModel()
    with pytest.raises(ValueError):
        FakeModel(script=["a"], policy=lambda m, t: ModelResponse(text="x"))


def test_usage_addition():
    total = Usage(1, 2, 1) + Usage(3, 4, 1)
    assert (total.input_tokens, total.output_tokens, total.model_calls) == (4, 6, 2)
