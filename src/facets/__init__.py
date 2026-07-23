"""Agentic FACETS — a framework-neutral runtime for classifying agent architectures.

The six axes: **F**eedback, **A**uthority, **C**ontrol, **E**xecution, **T**opology, **S**tate.
"""

from facets.agents import Agent, AgentResult, ExecutionContext, agent_as_tool
from facets.evaluation import EvalReport, Evaluator, Scorer
from facets.manifest import FacetsManifest, load_manifest
from facets.messages import Message, Role, ToolCall, ToolResult
from facets.models import DatabricksModel, FakeModel, ModelProvider, ModelResponse, Usage
from facets.state import InMemoryStateStore, StateStore, TaskState
from facets.tools import Tool, ToolRegistry, ToolSpec, tool
from facets.tracing import Span, Trace

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "AgentResult",
    "ExecutionContext",
    "agent_as_tool",
    "EvalReport",
    "Evaluator",
    "Scorer",
    "FacetsManifest",
    "load_manifest",
    "Message",
    "Role",
    "ToolCall",
    "ToolResult",
    "DatabricksModel",
    "FakeModel",
    "ModelProvider",
    "ModelResponse",
    "Usage",
    "InMemoryStateStore",
    "StateStore",
    "TaskState",
    "Tool",
    "ToolRegistry",
    "ToolSpec",
    "tool",
    "Span",
    "Trace",
    "__version__",
]
