"""Unit tests for the trace: deterministic timing, usage rollup, tool-call ordering."""

from facets.models import Usage
from facets.tracing import Trace


def make_clock(ticks):
    """A fake monotonic clock that returns the given values in order."""
    it = iter(ticks)
    return lambda: next(it)


def test_span_records_duration_deterministically():
    trace = Trace(clock=make_clock([10.0, 10.5, 20.0, 21.25]))
    with trace.span("decide", "model"):
        pass
    with trace.span("query_logs", "tool", tool="query_logs"):
        pass
    assert trace.spans[0].duration_s == 0.5
    assert trace.spans[1].duration_s == 1.25
    assert trace.total_duration_s == 1.75


def test_usage_rollup():
    trace = Trace()
    trace.record_usage(Usage(10, 5, 1))
    trace.record_usage(Usage(20, 7, 1))
    assert trace.input_tokens == 30
    assert trace.output_tokens == 12
    assert trace.total_tokens == 42
    assert trace.model_calls == 2


def test_tool_calls_ordered_and_filtered():
    trace = Trace(clock=make_clock([0, 1, 1, 2, 2, 3]))
    with trace.span("a:decide", "model"):
        pass
    with trace.span("a:query_logs", "tool", tool="query_logs"):
        pass
    with trace.span("a:query_metrics", "tool", tool="query_metrics"):
        pass
    assert trace.tool_calls == ["query_logs", "query_metrics"]


def test_summary_shape():
    trace = Trace(clock=make_clock([0, 1]))
    trace.record_usage(Usage(4, 6, 1))
    with trace.span("t", "tool", tool="t"):
        pass
    summary = trace.summary()
    assert summary["model_calls"] == 1
    assert summary["total_tokens"] == 10
    assert summary["tool_calls"] == ["t"]
