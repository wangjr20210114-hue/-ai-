"""Agent core package.

Stable imports for the platform-level Agent runtime. Legacy modules under
`agent/` re-export the same objects for compatibility.
"""
from agent.contracts import *  # noqa: F401,F403
from agent.events import *  # noqa: F401,F403
from agent.orchestrator import AgentOrchestrator
from agent.policy import AgentPolicy
from agent.runtime import AgentRuntime