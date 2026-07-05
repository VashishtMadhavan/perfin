"""Manual agent loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from perfin.agent.tools import TOOL_SCHEMAS, ToolDispatcher, tool_result_json


@dataclass(frozen=True, slots=True)
class AgentAnswer:
    text: str
    iterations: int
    tool_calls: int
    refused: bool = False


def run_agent_loop(
    question: str,
    *,
    client: Any,
    dispatcher: ToolDispatcher,
    max_iterations: int,
) -> AgentAnswer:
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    tool_calls = 0
    last_text = ""

    for iteration in range(1, max_iterations + 1):
        response = client.create_message(messages=messages, tools=TOOL_SCHEMAS)
        stop_reason = _get(response, "stop_reason")
        blocks = [_block_to_dict(block) for block in _get(response, "content", default=[])]
        text = _text_from_blocks(blocks)
        if text:
            last_text = text
        if stop_reason == "refusal":
            return AgentAnswer(text or "The model refused to answer.", iteration, tool_calls, True)

        tool_uses = [block for block in blocks if block.get("type") == "tool_use"]
        if not tool_uses:
            return AgentAnswer(text, iteration, tool_calls)

        messages.append({"role": "assistant", "content": blocks})
        result_blocks = []
        for tool_use in tool_uses:
            tool_calls += 1
            try:
                result = dispatcher.dispatch(
                    str(tool_use["name"]),
                    dict(tool_use.get("input") or {}),
                )
                result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use["id"],
                        "content": tool_result_json(result),
                    }
                )
            except Exception as exc:
                result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use["id"],
                        "is_error": True,
                        "content": str(exc),
                    }
                )
        messages.append({"role": "user", "content": result_blocks})

    return AgentAnswer(
        last_text or "I hit the tool-iteration limit before reaching a final answer.",
        max_iterations,
        tool_calls,
    )


def _text_from_blocks(blocks: list[dict[str, Any]]) -> str:
    return "".join(block.get("text", "") for block in blocks if block.get("type") == "text").strip()


def _block_to_dict(block: Any) -> dict[str, Any]:
    if isinstance(block, dict):
        return block
    kind = _get(block, "type")
    if kind == "text":
        return {"type": "text", "text": _get(block, "text", default="")}
    if kind == "tool_use":
        return {
            "type": "tool_use",
            "id": _get(block, "id"),
            "name": _get(block, "name"),
            "input": _get(block, "input", default={}),
        }
    return {"type": str(kind or "unknown")}


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)
