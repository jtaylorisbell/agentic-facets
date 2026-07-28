"""Unit tests for the model layer: FakeModel scripting/policy, usage accounting, retry backoff."""

from types import SimpleNamespace

import pytest

from facets.messages import Message
from facets.models import FakeModel, ModelResponse, Usage, _retry_after_seconds, call


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


# --- Rate-limit retry backoff (the pilot lost strong-model cells to this) --------------------


def _exc_with_headers(headers: dict | None):
    """A stand-in openai APIError carrying (or not) a response with headers."""
    if headers is None:
        return SimpleNamespace(response=None)
    return SimpleNamespace(response=SimpleNamespace(headers=headers))


def test_retry_after_numeric_seconds():
    exc = _exc_with_headers({"retry-after": "12"})
    assert _retry_after_seconds(exc) == 12.0


def test_retry_after_capitalized_header():
    exc = _exc_with_headers({"Retry-After": "5"})
    assert _retry_after_seconds(exc) == 5.0


def test_retry_after_absent_returns_none():
    assert _retry_after_seconds(_exc_with_headers({})) is None
    assert _retry_after_seconds(_exc_with_headers(None)) is None


def test_retry_after_garbage_returns_none():
    assert _retry_after_seconds(_exc_with_headers({"retry-after": "soon"})) is None


def test_retry_after_http_date_is_seconds_in_future():
    # A date ~an hour out should parse to a positive, ~3600s wait (allow slack for clock/parse).
    from email.utils import format_datetime

    from facets.models import _utcnow

    future = _utcnow().replace(microsecond=0)
    future = future.fromtimestamp(future.timestamp() + 3600, tz=future.tzinfo)
    exc = _exc_with_headers({"retry-after": format_datetime(future)})
    secs = _retry_after_seconds(exc)
    assert secs is not None and 3400 < secs <= 3600


def test_retry_delay_honors_retry_after_over_backoff():
    # With a Retry-After header, the delay should be ~that value (+ <1s jitter), not the
    # exponential backoff for the attempt number.
    from facets.models import DatabricksModel

    model = DatabricksModel(
        model="m", host="https://h", token="t", prefer_oauth=False, retry_max_delay=60
    )
    exc = _exc_with_headers({"retry-after": "10"})
    for attempt in range(5):
        delay = model._retry_delay(attempt, exc)
        assert 10.0 <= delay < 11.0  # server value + [0,1) jitter, independent of attempt


def test_retry_delay_jittered_backoff_within_ceiling():
    # No Retry-After -> full-jitter backoff in [0, base*2**attempt], capped at retry_max_delay.
    from facets.models import DatabricksModel

    model = DatabricksModel(
        model="m",
        host="https://h",
        token="t",
        prefer_oauth=False,
        retry_base_delay=1.0,
        retry_max_delay=8.0,
    )
    exc = _exc_with_headers(None)
    for attempt in range(10):
        delay = model._retry_delay(attempt, exc)
        assert 0.0 <= delay <= 8.0  # never exceeds the cap, even as 2**attempt explodes
