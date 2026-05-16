from __future__ import annotations

import json
from dataclasses import dataclass
from textwrap import shorten
from typing import Iterator, Protocol
from urllib import request

from app.runs.provider_transport import ProviderHttpTransport


@dataclass
class ProviderCapabilities:
    provider: str
    supports_streaming: bool
    supports_system_prompt: bool
    supports_temperature: bool
    supports_max_tokens: bool
    model_hint: str
    max_context_tokens: int
    quality_tier: int
    speed_tier: int
    cost_tier: int
    strengths: tuple[str, ...] = ()


@dataclass
class ProviderResult:
    output_text: str
    finish_reason: str | None = None


class LlmProvider(Protocol):
    name: str

    def capabilities(self) -> ProviderCapabilities: ...

    def complete(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ) -> ProviderResult: ...

    def stream(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ) -> Iterator[str]: ...


class LocalEchoProvider:
    name = "local_echo"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            supports_streaming=True,
            supports_system_prompt=True,
            supports_temperature=True,
            supports_max_tokens=True,
            model_hint="local_echo",
            max_context_tokens=32_000,
            quality_tier=1,
            speed_tier=5,
            cost_tier=1,
            strengths=("deterministic", "local-dev", "cheap"),
        )

    def complete(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ) -> ProviderResult:
        del model, temperature
        prompt_preview = shorten(" ".join(prompt.split()), width=1_600, placeholder=" ...")
        output = (
            "[local_echo completion]\n"
            f"system_prompt={system_prompt or 'none'}\n"
            "This is a deterministic local provider output for orchestrator wiring.\n"
            f"prompt_preview={prompt_preview}"
        )
        max_chars = max_output_tokens * 4
        return ProviderResult(output_text=output[:max_chars], finish_reason="stop")

    def stream(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ) -> Iterator[str]:
        result = self.complete(
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
        chunk_size = 160
        for index in range(0, len(result.output_text), chunk_size):
            yield result.output_text[index : index + chunk_size]


class OpenAIChatCompletionsProvider:
    name = "openai"

    def __init__(self, *, api_key: str, base_url: str, timeout_seconds: int = 60) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._transport = ProviderHttpTransport(
            provider="OpenAI",
            timeout_seconds=timeout_seconds,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            supports_streaming=True,
            supports_system_prompt=True,
            supports_temperature=True,
            supports_max_tokens=True,
            model_hint="gpt-5.4",
            max_context_tokens=128_000,
            quality_tier=5,
            speed_tier=4,
            cost_tier=4,
            strengths=("planning", "implementation", "tool-use"),
        )

    def complete(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ) -> ProviderResult:
        payload = self._build_payload(
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            stream=False,
        )
        response = self._transport.request_json(self._request(payload))
        try:
            choices = response["choices"]
            choice = choices[0] if isinstance(choices, list) else None
            message = choice["message"]["content"] if isinstance(choice, dict) else None
        except (KeyError, TypeError, IndexError) as exc:
            raise RuntimeError("Malformed OpenAI response payload") from exc
        if not isinstance(message, str):
            message = str(message)
        finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        return ProviderResult(output_text=message, finish_reason=finish_reason)

    def stream(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ) -> Iterator[str]:
        payload = self._build_payload(
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            stream=True,
        )
        yield from self._transport.stream_sse_json(self._request(payload), _openai_stream_chunk)

    def _build_payload(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
        stream: bool,
    ) -> dict[str, object]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return {
            "model": model,
            "messages": messages,
            "max_completion_tokens": max_output_tokens,
            "temperature": temperature,
            "stream": stream,
        }

    def _request(self, payload: dict[str, object]) -> request.Request:
        return request.Request(
            url=f"{self._base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )


class CodexSidecarProvider(OpenAIChatCompletionsProvider):
    name = "codex_sidecar"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            supports_streaming=True,
            supports_system_prompt=True,
            supports_temperature=True,
            supports_max_tokens=True,
            model_hint="codex",
            max_context_tokens=128_000,
            quality_tier=4,
            speed_tier=3,
            cost_tier=2,
            strengths=("experimental", "local-sidecar", "chatgpt-oauth-bridge"),
        )


class AnthropicMessagesProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        api_version: str,
        timeout_seconds: int = 60,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._api_version = api_version
        self._transport = ProviderHttpTransport(
            provider="Anthropic",
            timeout_seconds=timeout_seconds,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            supports_streaming=False,
            supports_system_prompt=True,
            supports_temperature=True,
            supports_max_tokens=True,
            model_hint="claude-3-7-sonnet-latest",
            max_context_tokens=200_000,
            quality_tier=5,
            speed_tier=3,
            cost_tier=4,
            strengths=("review", "long-context", "writing"),
        )

    def complete(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ) -> ProviderResult:
        payload: dict[str, object] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_output_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt
        parsed = self._transport.request_json(
            request.Request(
                url=f"{self._base_url}/v1/messages",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": self._api_version,
                    "content-type": "application/json",
                },
                method="POST",
            )
        )
        try:
            content = parsed["content"]
            text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
            output = "\n".join([part for part in text_parts if part])
            finish_reason = parsed.get("stop_reason")
        except (KeyError, TypeError) as exc:
            raise RuntimeError("Malformed Anthropic response payload") from exc
        return ProviderResult(output_text=output, finish_reason=finish_reason)

    def stream(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ) -> Iterator[str]:
        result = self.complete(
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
        yield result.output_text


class GeminiGenerateContentProvider:
    name = "gemini"

    def __init__(self, *, api_key: str, base_url: str, timeout_seconds: int = 60) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._transport = ProviderHttpTransport(
            provider="Gemini",
            timeout_seconds=timeout_seconds,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            supports_streaming=False,
            supports_system_prompt=True,
            supports_temperature=True,
            supports_max_tokens=True,
            model_hint="gemini-2.5-pro",
            max_context_tokens=1_000_000,
            quality_tier=4,
            speed_tier=4,
            cost_tier=3,
            strengths=("large-context", "analysis", "multimodal-ready"),
        )

    def complete(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ) -> ProviderResult:
        user_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        payload: dict[str, object] = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }
        parsed = self._transport.request_json(
            request.Request(
                url=f"{self._base_url}/v1beta/models/{model}:generateContent?key={self._api_key}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"content-type": "application/json"},
                method="POST",
            )
        )
        try:
            candidates = parsed["candidates"]
            candidate = candidates[0] if isinstance(candidates, list) else None
            content = candidate["content"]["parts"] if isinstance(candidate, dict) else []
            output = "\n".join([part.get("text", "") for part in content if isinstance(part, dict)])
            finish_reason = candidate.get("finishReason") if isinstance(candidate, dict) else None
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Malformed Gemini response payload") from exc
        return ProviderResult(output_text=output, finish_reason=finish_reason)

    def stream(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None,
        max_output_tokens: int,
        temperature: float,
    ) -> Iterator[str]:
        result = self.complete(
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
        yield result.output_text


def _openai_stream_chunk(event: dict[str, object]) -> str | None:
    try:
        choices = event["choices"]
        if not isinstance(choices, list) or not choices:
            return None
        choice = choices[0]
        if not isinstance(choice, dict):
            return None
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            return None
        content = delta.get("content")
        return content if isinstance(content, str) and content else None
    except (KeyError, TypeError):
        return None
