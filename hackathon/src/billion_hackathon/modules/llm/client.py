"""Single entry for all model calls.

Providers are selected by BILLION_LLM_PROVIDER env var:
  stub      – deterministic echo, no network (default)
  openai    – any OpenAI-compatible endpoint (OpenAI, OpenRouter, local Ollama, …)
  anthropic – Anthropic Messages API

Set at minimum:
  BILLION_LLM_PROVIDER=openai   (or anthropic)
  BILLION_LLM_API_KEY=sk-…
  BILLION_LLM_MODEL=gpt-4o      (or claude-3-5-sonnet-20241022, etc.)

Optional:
  BILLION_LLM_BASE_URL=https://api.openai.com/v1   (override for openai-compatible endpoints)
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Content types (multimodal support)
# ---------------------------------------------------------------------------


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImagePart(BaseModel):
    """Base64-encoded image ready to embed in a message."""

    type: Literal["image"] = "image"
    data: str        # base64-encoded bytes (no data-URI prefix)
    media_type: str  # e.g. "image/jpeg", "image/png", "image/webp"


ContentPart = Annotated[TextPart | ImagePart, Field(discriminator="type")]


# ---------------------------------------------------------------------------
# Message / response contracts
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str  # "system" | "user" | "assistant"
    content: str | list[ContentPart]


class LLMResponse(BaseModel):
    text: str
    model: str = "stub"
    raw: dict = Field(default_factory=dict)


class LLMClient(Protocol):
    def complete(self, messages: list[ChatMessage], *, max_tokens: int = 1024) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# Stub (default — no network, deterministic)
# ---------------------------------------------------------------------------


class StubLLMClient:
    model_name: str = "stub"

    def complete(self, messages: list[ChatMessage], *, max_tokens: int = 1024) -> LLMResponse:
        last_user = next(
            (
                m.content if isinstance(m.content, str) else "[multimodal message]"
                for m in reversed(messages)
                if m.role == "user"
            ),
            "",
        )
        return LLMResponse(
            text=f"[stub-echo] {last_user[:2000]}",
            model=self.model_name,
            raw={"messages_n": len(messages), "max_tokens": max_tokens},
        )


# ---------------------------------------------------------------------------
# OpenAI-compatible client
# ---------------------------------------------------------------------------


def _openai_content(content: str | list[ContentPart]) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        return content
    parts: list[dict[str, Any]] = []
    for p in content:
        if isinstance(p, TextPart):
            parts.append({"type": "text", "text": p.text})
        else:
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{p.media_type};base64,{p.data}"},
                }
            )
    return parts


class OpenAICompatibleClient:
    """Works with OpenAI, OpenRouter, Together AI, Ollama, and any /v1/chat/completions endpoint."""

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def complete(self, messages: list[ChatMessage], *, max_tokens: int = 1024) -> LLMResponse:
        import httpx

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": m.role, "content": _openai_content(m.content)} for m in messages
            ],
        }
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        text: str = data["choices"][0]["message"]["content"]
        return LLMResponse(text=text, model=self.model, raw=data)


# ---------------------------------------------------------------------------
# Anthropic client (native Messages API)
# ---------------------------------------------------------------------------


def _anthropic_content(content: str | list[ContentPart]) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    parts: list[dict[str, Any]] = []
    for p in content:
        if isinstance(p, TextPart):
            parts.append({"type": "text", "text": p.text})
        else:
            parts.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": p.media_type,
                        "data": p.data,
                    },
                }
            )
    return parts


class AnthropicClient:
    _API_BASE = "https://api.anthropic.com/v1"
    _API_VERSION = "2023-06-01"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def complete(self, messages: list[ChatMessage], *, max_tokens: int = 1024) -> LLMResponse:
        import httpx

        system_msgs = [m for m in messages if m.role == "system"]
        other_msgs = [m for m in messages if m.role != "system"]

        system_text = "\n\n".join(
            m.content
            if isinstance(m.content, str)
            else " ".join(p.text for p in m.content if isinstance(p, TextPart))
            for m in system_msgs
        )

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": m.role, "content": _anthropic_content(m.content)} for m in other_msgs
            ],
        }
        if system_text:
            payload["system"] = system_text

        resp = httpx.post(
            f"{self._API_BASE}/messages",
            json=payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self._API_VERSION,
                "content-type": "application/json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        text: str = data["content"][0]["text"]
        return LLMResponse(text=text, model=self.model, raw=data)


# ---------------------------------------------------------------------------
# Factory — reads env vars, returns the right client
# ---------------------------------------------------------------------------


def get_llm_client() -> LLMClient:
    """Return the configured LLM client based on BILLION_LLM_PROVIDER."""
    provider = os.environ.get("BILLION_LLM_PROVIDER", "stub").lower().strip()

    if provider == "stub":
        return StubLLMClient()

    api_key = os.environ.get("BILLION_LLM_API_KEY", "")
    model = os.environ.get("BILLION_LLM_MODEL", "")

    if provider == "anthropic":
        return AnthropicClient(
            api_key=api_key,
            model=model or "claude-3-5-sonnet-20241022",
        )

    # Default: openai-compatible
    base_url = os.environ.get("BILLION_LLM_BASE_URL", "https://api.openai.com/v1")
    return OpenAICompatibleClient(
        api_key=api_key,
        model=model or "gpt-4o",
        base_url=base_url,
    )
