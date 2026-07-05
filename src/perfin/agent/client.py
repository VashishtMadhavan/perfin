"""Anthropic client adapter."""

from __future__ import annotations

from typing import Any

import anthropic

from perfin.config import LLMSettings
from perfin.agent.prompts import SYSTEM_BLOCK


class AnthropicAgentClient:
    def __init__(self, settings: LLMSettings) -> None:
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for perfin ask.")
        self._settings = settings
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def create_message(self, *, messages: list[dict], tools: list[dict]) -> Any:
        kwargs: dict[str, Any] = {
            "model": self._settings.model,
            "max_tokens": 1200,
            "system": [SYSTEM_BLOCK],
            "messages": messages,
            "tools": tools,
        }
        if "fable" in self._settings.model:
            kwargs["output_config"] = {"effort": self._settings.effort}
            kwargs["betas"] = ["server-side-fallback-2026-06-01"]
            kwargs["fallbacks"] = [{"model": "claude-opus-4-8"}]
        else:
            kwargs["temperature"] = 0
        return self._client.beta.messages.create(**kwargs)
