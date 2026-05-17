from __future__ import annotations

from services.orchestrator.app.experimental_auth import (
    ExperimentalCodexAuthProvider,
    FileTokenStore,
    TokenBundle,
    storage_is_secure,
)
from services.orchestrator.app.experimental_auth.codex_client import _extract_id_token_metadata
from services.orchestrator.app.experimental_auth.pkce import generate_pkce_codes, generate_state


def test_file_token_store_round_trip(tmp_path) -> None:
    path = tmp_path / "token.json"
    store = FileTokenStore(path)
    bundle = TokenBundle(
        provider="codex_oauth_experimental",
        access_token="token-123",
        refresh_token="refresh-456",
        expires_at="2026-05-20T12:00:00Z",
        metadata={"plan": "plus"},
    )

    store.save(bundle)
    loaded = store.load()

    assert loaded is not None
    assert loaded.access_token == "token-123"
    assert loaded.refresh_token == "refresh-456"
    assert loaded.metadata["plan"] == "plus"
    assert storage_is_secure(path) is True


def test_pkce_codes_are_generated() -> None:
    codes = generate_pkce_codes()
    state = generate_state()

    assert len(codes.code_verifier) >= 43
    assert len(codes.code_challenge) >= 43
    assert state


def test_codex_auth_status_reports_prototype(tmp_path) -> None:
    path = tmp_path / "codex-token.json"
    provider = ExperimentalCodexAuthProvider(store=FileTokenStore(path))

    status = provider.status()

    assert status.provider == "codex_oauth_experimental"
    assert status.implementation_state == "prototype"
    assert status.authenticated is False
    assert status.storage_secure is False
    assert "direct execution" in status.detail


def test_codex_auth_refresh_uses_saved_refresh_token(tmp_path) -> None:
    path = tmp_path / "codex-token.json"

    class _Client:
        def refresh_tokens(self, refresh_token: str) -> TokenBundle:
            assert refresh_token == "refresh-456"
            return TokenBundle(
                provider="codex_oauth_experimental",
                access_token="token-789",
                refresh_token="refresh-456",
                expires_at="2026-05-20T12:00:00Z",
                metadata={"plan": "plus"},
            )

    provider = ExperimentalCodexAuthProvider(store=FileTokenStore(path), client=_Client())
    provider.save(
        TokenBundle(
            provider="codex_oauth_experimental",
            access_token="token-123",
            refresh_token="refresh-456",
        )
    )

    refreshed = provider.refresh()

    assert refreshed.access_token == "token-789"
    assert provider.load() is not None
    assert provider.load().access_token == "token-789"  # type: ignore[union-attr]


def test_extract_id_token_metadata_handles_invalid_token() -> None:
    assert _extract_id_token_metadata("not-a-jwt") == {}


def test_codex_auth_status_reports_secure_storage_after_save(tmp_path) -> None:
    path = tmp_path / "codex-token.json"
    provider = ExperimentalCodexAuthProvider(store=FileTokenStore(path))
    provider.save(
        TokenBundle(
            provider="codex_oauth_experimental",
            access_token="token-123",
            refresh_token="refresh-456",
        )
    )

    status = provider.status()

    assert status.authenticated is True
    assert status.storage_secure is True


def test_start_browser_login_reuses_pending_flow(tmp_path) -> None:
    path = tmp_path / "codex-token.json"

    class _Client:
        pass

    provider = ExperimentalCodexAuthProvider(store=FileTokenStore(path), client=_Client())
    original_complete = provider._complete_browser_login

    def _fake_complete(flow) -> None:
        return None

    provider._complete_browser_login = _fake_complete  # type: ignore[method-assign]
    try:
        first = provider.start_browser_login(callback_port=1457)
        second = provider.start_browser_login(callback_port=1457)
    finally:
        provider._complete_browser_login = original_complete  # type: ignore[method-assign]
        pending = type(provider)._browser_flow
        if pending is not None:
            pending.server.stop()
            type(provider)._browser_flow = None

    assert first == second
    assert "auth.openai.com/oauth/authorize" in first
