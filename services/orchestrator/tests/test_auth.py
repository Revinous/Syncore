from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routes.auth import get_codex_auth_provider, get_openai_auth_service
from app.experimental_auth.models import ExperimentalAuthStatus, TokenBundle
from app.main import create_app
from app.services.local_auth_service import OpenAIAuthStatus


class _FakeOpenAIService:
    def __init__(self) -> None:
        self.configured = False
        self.models = ["gpt-5", "gpt-5-mini"]

    def status(self) -> OpenAIAuthStatus:
        return OpenAIAuthStatus(
            configured=self.configured,
            storage_secure=self.configured,
            token_path="/tmp/openai_credentials.json",
            detail="configured" if self.configured else "not configured",
        )

    def save_api_key(self, api_key: str) -> list[str]:
        if api_key == "bad-key":
            raise RuntimeError("OpenAI API rejected this key")
        self.configured = True
        return self.models

    def list_models(self) -> list[str]:
        if not self.configured:
            raise RuntimeError("No local OpenAI API key is configured.")
        return self.models

    def clear(self) -> None:
        self.configured = False


class _FakeCodexProvider:
    def __init__(self) -> None:
        self.authenticated = False
        self.can_refresh = False

    def start_browser_login(self) -> str:
        return "http://localhost/auth"

    def refresh(self) -> TokenBundle:
        self.authenticated = True
        self.can_refresh = True
        return TokenBundle(provider="codex_oauth_experimental", access_token="token-456")

    def clear(self) -> None:
        self.authenticated = False
        self.can_refresh = False

    def status(self) -> ExperimentalAuthStatus:
        return ExperimentalAuthStatus(
            provider="codex_oauth_experimental",
            mode="experimental",
            implementation_state="prototype",
            authenticated=self.authenticated,
            can_refresh=self.can_refresh,
            storage_secure=self.authenticated,
            token_path="/tmp/codex/token.json",
            expires_at=None,
            detail="codex status",
            metadata={},
        )


def test_openai_auth_routes_round_trip() -> None:
    app = create_app()
    service = _FakeOpenAIService()
    app.dependency_overrides[get_openai_auth_service] = lambda: service
    client = TestClient(app)

    status = client.get("/auth/openai/status")
    assert status.status_code == 200
    assert status.json()["configured"] is False

    login = client.post("/auth/openai/login", json={"api_key": "sk-test"})
    assert login.status_code == 200
    assert login.json()["configured"] is True
    assert login.json()["models"] == ["gpt-5", "gpt-5-mini"]

    logout = client.post("/auth/openai/logout")
    assert logout.status_code == 200
    assert logout.json()["configured"] is False


def test_codex_auth_routes_round_trip() -> None:
    app = create_app()
    provider = _FakeCodexProvider()
    app.dependency_overrides[get_codex_auth_provider] = lambda: provider
    client = TestClient(app)

    status = client.get("/auth/codex/status")
    assert status.status_code == 200
    assert status.json()["authenticated"] is False

    login = client.post("/auth/codex/login/browser")
    assert login.status_code == 200
    assert login.json()["pending"] is True
    assert login.json()["auth_url"] == "http://localhost/auth"

    refresh = client.post("/auth/codex/refresh")
    assert refresh.status_code == 200
    assert refresh.json()["authenticated"] is True

    logout = client.post("/auth/codex/logout")
    assert logout.status_code == 200
    assert logout.json()["authenticated"] is False
