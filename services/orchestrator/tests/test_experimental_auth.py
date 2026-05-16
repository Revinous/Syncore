from __future__ import annotations

from services.orchestrator.app.experimental_auth import (
    ExperimentalCodexAuthProvider,
    FileTokenStore,
    TokenBundle,
)


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


def test_codex_auth_status_reports_not_implemented(tmp_path) -> None:
    path = tmp_path / "codex-token.json"
    provider = ExperimentalCodexAuthProvider(store=FileTokenStore(path))

    status = provider.status()

    assert status.provider == "codex_oauth_experimental"
    assert status.implementation_state == "not_implemented"
    assert status.authenticated is False
    assert "codex_sidecar" in status.detail
