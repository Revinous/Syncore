from __future__ import annotations

import json
from dataclasses import dataclass
from textwrap import shorten
from typing import Iterator, Protocol
from urllib import error, request


@dataclass
class ProviderCapabilities:
    provider: str
    supports_streaming: bool
    supports_system_prompt: bool
    supports_temperature: bool
    supports_max_tokens: bool
    model_hint: str


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
        self._timeout_seconds = timeout_seconds

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            supports_streaming=True,
            supports_system_prompt=True,
            supports_temperature=True,
            supports_max_tokens=True,
            model_hint="gpt-5.4",
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
        response = self._request_json(payload)
        try:
            choice = response["choices"][0]
            message = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as error_exc:
            raise RuntimeError("Malformed OpenAI response payload") from error_exc

        if not isinstance(message, str):
            message = str(message)

        finish_reason = choice.get("finish_reason")
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
        req = request.Request(
            url=f"{self._base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self._timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    payload_line = line[6:]
                    if payload_line == "[DONE]":
                        break
                    try:
                        event = json.loads(payload_line)
                        delta = event["choices"][0]["delta"].get("content")
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
                    if delta:
                        yield delta
        except error.HTTPError as http_error:
            body = http_error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI provider HTTP {http_error.code}: {body}") from http_error
        except error.URLError as url_error:
            raise RuntimeError(
                f"OpenAI provider connection failed: {url_error.reason}"
            ) from url_error

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

    def _request_json(self, payload: dict[str, object]) -> dict[str, object]:
        req = request.Request(
            url=f"{self._base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self._timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise RuntimeError("OpenAI response payload is not an object")
                return parsed
        except error.HTTPError as http_error:
            body = http_error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI provider HTTP {http_error.code}: {body}") from http_error
        except error.URLError as url_error:
            raise RuntimeError(
                f"OpenAI provider connection failed: {url_error.reason}"
            ) from url_error


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
        self._timeout_seconds = timeout_seconds

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            supports_streaming=False,
            supports_system_prompt=True,
            supports_temperature=True,
            supports_max_tokens=True,
            model_hint="claude-3-7-sonnet-latest",
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

        req = request.Request(
            url=f"{self._base_url}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": self._api_version,
                "content-type": "application/json",
            },
            method="POST",
        )
        parsed = _request_json(req, self._timeout_seconds, "Anthropic")
        try:
            content = parsed["content"]
            text_parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            output = "\n".join([part for part in text_parts if part])
            finish_reason = parsed.get("stop_reason")
        except (KeyError, TypeError) as error_exc:
            raise RuntimeError("Malformed Anthropic response payload") from error_exc
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
        self._timeout_seconds = timeout_seconds

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            supports_streaming=False,
            supports_system_prompt=True,
            supports_temperature=True,
            supports_max_tokens=True,
            model_hint="gemini-2.5-pro",
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
        user_prompt = prompt
        if system_prompt:
            user_prompt = f"{system_prompt}\n\n{prompt}"
        payload: dict[str, object] = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }
        req = request.Request(
            url=(
                f"{self._base_url}/v1beta/models/{model}:generateContent"
                f"?key={self._api_key}"
            ),
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        parsed = _request_json(req, self._timeout_seconds, "Gemini")
        try:
            candidates = parsed["candidates"]
            content = candidates[0]["content"]["parts"]
            output = "\n".join(
                [part.get("text", "") for part in content if isinstance(part, dict)]
            )
            finish_reason = candidates[0].get("finishReason")
        except (KeyError, IndexError, TypeError) as error_exc:
            raise RuntimeError("Malformed Gemini response payload") from error_exc
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


def _request_json(req: request.Request, timeout_seconds: int, label: str) -> dict[str, object]:
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise RuntimeError(f"{label} response payload is not an object")
            return parsed
    except error.HTTPError as http_error:
        body = http_error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{label} provider HTTP {http_error.code}: {body}") from http_error
    except error.URLError as url_error:
        raise RuntimeError(f"{label} provider connection failed: {url_error.reason}") from url_error
