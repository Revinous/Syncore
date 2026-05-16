from __future__ import annotations

from .client import SyncoreApiClient
from .config import load_config
from .local_runtime import ensure_api_running, ensure_web_running, open_browser
from .openai_auth import OpenAIAuthStore, OpenAIModelClient
from .tui import SyncoreTuiApp
from services.orchestrator.app.experimental_auth import ExperimentalCodexAuthProvider


def build_client(config=None) -> SyncoreApiClient:
    if config is None:
        config = load_config()
    return SyncoreApiClient(config.api_url, config.timeout_seconds)


def build_client_for_commands(config=None) -> SyncoreApiClient:
    if config is None:
        return build_client()
    return build_client(config)


def start_api(config) -> None:
    ensure_api_running(client=build_client(config), api_url=config.api_url)


def start_web() -> str:
    return ensure_web_running()


def try_open_browser(url: str) -> bool:
    return open_browser(url)


def launch_tui(config, selected_workspace_id: str | None, selected_workspace_name: str | None) -> None:
    SyncoreTuiApp(
        config,
        selected_workspace_id=selected_workspace_id,
        selected_workspace_name=selected_workspace_name,
    ).run()


def openai_store() -> OpenAIAuthStore:
    return OpenAIAuthStore()


def openai_models_client(config=None) -> OpenAIModelClient:
    if config is None:
        config = load_config()
    return OpenAIModelClient(timeout_seconds=config.timeout_seconds)


def codex_auth_provider() -> ExperimentalCodexAuthProvider:
    return ExperimentalCodexAuthProvider()
