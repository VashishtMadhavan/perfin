from __future__ import annotations

import json

from perfin.agent.loop import run_agent_loop
from perfin.agent.tools import ToolDispatcher
from perfin.core.finance_service import FinanceService
from perfin.core.sync_service import SyncService
from perfin.datasources.fake_source import FakeDataSource
from perfin.storage.db import create_db_engine, create_session_factory, init_schema


def _session_factory():
    engine = create_db_engine("sqlite:///:memory:")
    init_schema(engine)
    return create_session_factory(engine)


def test_agent_loop_dispatches_tool_and_returns_final_answer() -> None:
    sessions = _session_factory()
    SyncService(sessions).sync(FakeDataSource())
    client = _ScriptedClient(
        [
            {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "get_spending_summary",
                        "input": {"months": 3, "group_by": "category"},
                    }
                ],
            },
            {
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": "Your three-month spending was $10,591.29.",
                    }
                ],
            },
        ]
    )

    answer = run_agent_loop(
        "How much did I spend?",
        client=client,
        dispatcher=ToolDispatcher(FinanceService(sessions)),
        max_iterations=5,
    )

    assert answer.text == "Your three-month spending was $10,591.29."
    assert answer.tool_calls == 1
    tool_result = client.calls[1]["messages"][-1]["content"][0]
    result = json.loads(tool_result["content"])
    assert result["total"] == "10591.29"


def test_agent_loop_stops_at_iteration_limit() -> None:
    sessions = _session_factory()
    SyncService(sessions).sync(FakeDataSource())
    client = _ScriptedClient(
        [
            {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "get_current_date",
                        "input": {},
                    }
                ],
            },
            {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_2",
                        "name": "get_current_date",
                        "input": {},
                    }
                ],
            },
        ]
    )

    answer = run_agent_loop(
        "Loop please",
        client=client,
        dispatcher=ToolDispatcher(FinanceService(sessions)),
        max_iterations=2,
    )

    assert "iteration limit" in answer.text
    assert answer.tool_calls == 2


class _ScriptedClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create_message(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)
