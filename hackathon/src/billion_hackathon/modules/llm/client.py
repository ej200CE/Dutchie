"""Single entry for model calls — stubs today; add HTTP provider behind env flags."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str  # "system" | "user" | "assistant"
    content: str


class LLMResponse(BaseModel):
    text: str
    model: str = "stub"
    raw: dict = Field(default_factory=dict)


class LLMClient(Protocol):
    def complete(self, messages: list[ChatMessage], *, max_tokens: int = 1024) -> LLMResponse: ...


class StubLLMClient:
    """Returns deterministic text for dev/tests; simulates latency-free provider."""

    model_name: str = "stub"

    def complete(self, messages: list[ChatMessage], *, max_tokens: int = 1024) -> LLMResponse:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return LLMResponse(
            text=f"[stub-echo] {last_user[:2000]}",
            model=self.model_name,
            raw={"messages_n": len(messages), "max_tokens": max_tokens},
        )


def get_llm_client() -> LLMClient:
    """Return the active client. Wire `BILLION_LLM_*` env + httpx when you add a live provider."""
    return StubLLMClient()
