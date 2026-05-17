from __future__ import annotations

from typing import Iterator

from app.runs.providers import CodexOAuthExperimentalProvider


class _FakeAuthProvider:
    def __init__(self, token: str = "oauth-token") -> None:
        self._token = token

    def current_access_token(self) -> str | None:
        return self._token


def test_codex_oauth_experimental_provider_complete_aggregates_stream_chunks() -> None:
    provider = CodexOAuthExperimentalProvider(auth_provider=_FakeAuthProvider())

    def fake_stream_sse_json(request, chunk_extractor) -> Iterator[str]:
        assert request.full_url == "https://chatgpt.com/backend-api/codex/responses"
        assert request.get_header("Authorization") == "Bearer oauth-token"
        assert request.get_header("Accept") == "text/event-stream"
        payload = request.data.decode("utf-8")
        assert '"model": "gpt-5.5"' in payload
        assert '"stream": true' in payload
        assert '"store": false' in payload
        assert '"temperature"' not in payload
        assert '"max_output_tokens"' not in payload
        first = chunk_extractor({"type": "response.output_text.delta", "delta": "SYNC"})
        second = chunk_extractor({"type": "response.output_text.delta", "delta": "ORE"})
        if first:
            yield first
        if second:
            yield second

    provider._transport.stream_sse_json = fake_stream_sse_json  # type: ignore[method-assign]

    result = provider.complete(
        model="gpt-5.5",
        prompt="Reply with exactly SYNCORE",
        system_prompt="You are Syncore.",
        max_output_tokens=128,
        temperature=0.1,
    )

    assert result.output_text == "SYNCORE"
    assert result.finish_reason == "stop"
    capabilities = provider.capabilities()
    assert capabilities.supports_temperature is False
    assert capabilities.supports_max_tokens is False


def test_codex_oauth_experimental_provider_requires_access_token() -> None:
    provider = CodexOAuthExperimentalProvider(auth_provider=_FakeAuthProvider(token=""))

    try:
        provider.complete(
            model="gpt-5.5",
            prompt="test",
            system_prompt=None,
            max_output_tokens=128,
            temperature=0.1,
        )
    except RuntimeError as error:
        assert "no current access token" in str(error)
    else:
        raise AssertionError("Expected RuntimeError when no native OAuth access token exists")
