from __future__ import annotations

import unittest

from agent.contracts import AgentPlan, ExecutionStatus, PermissionLevel
from agent.events import AgentEvent
from agent.runtime import AgentRuntime


class AgentRuntimeTests(unittest.TestCase):
    def test_run_lifecycle_is_recorded(self) -> None:
        runtime = AgentRuntime()
        event = AgentEvent.user_activity("session-1", "hello")
        run = runtime.start_run(event)
        plan = AgentPlan(
            run_id=run.run_id,
            session_id=event.session_id,
            event_type=event.type,
            user_message=event.text,
            intent="chat",
            permission_level=PermissionLevel.AUTO,
        )

        runtime.attach_plan(run, plan)
        runtime.finish(run, ExecutionStatus.SUCCEEDED)

        self.assertEqual(run.status, ExecutionStatus.SUCCEEDED)
        self.assertIsNotNone(run.ended_at)
        self.assertEqual(runtime.get_session_runs("session-1"), [run])
        self.assertIn(ExecutionStatus.PLANNED, [item.status for item in run.observations])
