from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.experimental_auth import ExperimentalCodexAuthProvider
from app.store_factory import build_memory_store

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])
class TaskDiagnostics(BaseModel):
    task_id: UUID
    task_exists: bool
    agent_run_count: int
    baton_packet_count: int
    event_count: int


class ExperimentalProviderDiagnostics(BaseModel):
    provider: str
    mode: str
    warning: str
    recommended_action: str
    provider_registered: bool
    executable: bool
    detail: str | None = None
    required_settings: list[str] = Field(default_factory=list)
    enabled: bool | None = None
    configured: bool | None = None
    api_key_configured: bool | None = None
    base_url: str | None = None
    reachable: bool | None = None
    implementation_state: str | None = None
    authenticated: bool | None = None
    can_refresh: bool | None = None
    storage_secure: bool | None = None
    token_path: str | None = None
    expires_at: str | None = None


class DiagnosticsConfig(BaseModel):
    environment: str
    runtime_mode: str
    db_backend: str
    redis_required: bool
    redis_url: str
    postgres_dsn: str
    sqlite_db_path: str
    codex_sidecar: ExperimentalProviderDiagnostics
    codex_oauth_experimental: ExperimentalProviderDiagnostics


class DiagnosticsOverview(BaseModel):
    service: str
    environment: str
    runtime_mode: str
    db_backend: str
    redis_required: bool
    codex_sidecar: ExperimentalProviderDiagnostics
    codex_oauth_experimental: ExperimentalProviderDiagnostics


class DiagnosticsRoutes(BaseModel):
    routes: list[str]
@router.get("/task/{task_id}", response_model=TaskDiagnostics)
def diagnostics_for_task(
    task_id: UUID,
    settings: Settings = Depends(get_settings),
) -> TaskDiagnostics:
    store = build_memory_store(settings)
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    runs = store.list_agent_runs(task_id)
    packets = store.list_baton_packets(task_id)
    events = store.list_project_events(task_id)

    return TaskDiagnostics(
        task_id=task_id,
        task_exists=True,
        agent_run_count=len(runs),
        baton_packet_count=len(packets),
        event_count=len(events),
    )


@router.get("", response_model=DiagnosticsOverview)
def diagnostics_overview(settings: Settings = Depends(get_settings)) -> DiagnosticsOverview:
    return DiagnosticsOverview(
        service="orchestrator",
        environment=settings.environment,
        runtime_mode=settings.syncore_runtime_mode,
        db_backend=settings.syncore_db_backend,
        redis_required=settings.redis_required,
        codex_sidecar=_codex_sidecar_status(settings),
        codex_oauth_experimental=_codex_oauth_experimental_status(),
    )
@router.get("/config", response_model=DiagnosticsConfig)
def diagnostics_config(settings: Settings = Depends(get_settings)) -> DiagnosticsConfig:
    return DiagnosticsConfig(
        environment=settings.environment,
        runtime_mode=settings.syncore_runtime_mode,
        db_backend=settings.syncore_db_backend,
        redis_required=settings.redis_required,
        redis_url=_redact_connection_value(settings.redis_url),
        postgres_dsn=_redact_connection_value(settings.postgres_dsn),
        sqlite_db_path=settings.sqlite_db_path,
        codex_sidecar=_codex_sidecar_status(settings),
        codex_oauth_experimental=_codex_oauth_experimental_status(),
    )
@router.get("/routes", response_model=DiagnosticsRoutes)
def diagnostics_routes(request: Request) -> DiagnosticsRoutes:
    paths = sorted(
        {
            f"{','.join(sorted(route.methods or []))} {route.path}"
            for route in request.app.routes
            if getattr(route, "path", None)
        }
    )
    return DiagnosticsRoutes(routes=paths)


def _redact_connection_value(value: str) -> str:
    if "@" in value:
        head, tail = value.rsplit("@", 1)
        if "://" in head:
            scheme, _ = head.split("://", 1)
            return f"{scheme}://***@{tail}"
    return "***"


def _codex_sidecar_status(settings: Settings) -> ExperimentalProviderDiagnostics:
    base_url = settings.codex_sidecar_base_url.strip() or None
    api_key = (settings.codex_sidecar_api_key or "").strip()
    enabled = settings.codex_sidecar_enabled
    configured = enabled and bool(base_url) and bool(api_key)
    reachable = False
    detail = "disabled"
    recommended_action = (
        "Keep this disabled unless you intentionally want Syncore to route through a local "
        "CLIProxyAPI-style bridge."
    )
    if enabled and not base_url:
        detail = "enabled but base URL is missing"
        recommended_action = (
            "Set CODEX_SIDECAR_BASE_URL and re-run `syncore diagnostics`. Official OpenAI "
            "Platform usage still relies on OPENAI_API_KEY instead."
        )
    elif enabled and not api_key:
        detail = "enabled but API key is missing"
        recommended_action = (
            "Set CODEX_SIDECAR_API_KEY and re-run `syncore diagnostics`. Do not treat this as "
            "a replacement for official OpenAI API-key mode."
        )
    elif configured and base_url:
        reachable, detail = _probe_codex_sidecar(base_url, api_key)
        if reachable:
            recommended_action = (
                "The sidecar is reachable. Select provider `codex_sidecar` explicitly for tasks "
                "that should use the experimental bridge."
            )
        else:
            recommended_action = (
                "Start the local sidecar and verify CODEX_SIDECAR_BASE_URL and "
                "CODEX_SIDECAR_API_KEY, then re-run `syncore diagnostics`."
            )
    return ExperimentalProviderDiagnostics(
        provider="codex_sidecar",
        mode="experimental",
        warning=(
            "Experimental local ChatGPT/Codex sidecar bridge. This is distinct from official "
            "OpenAI Platform API authentication."
        ),
        recommended_action=recommended_action,
        provider_registered=configured,
        executable=configured and reachable,
        detail=detail,
        required_settings=[
            "CODEX_SIDECAR_ENABLED",
            "CODEX_SIDECAR_BASE_URL",
            "CODEX_SIDECAR_API_KEY",
        ],
        enabled=enabled,
        configured=configured,
        api_key_configured=bool(api_key),
        base_url=base_url,
        reachable=reachable,
    )


def _codex_oauth_experimental_status() -> ExperimentalProviderDiagnostics:
    provider = ExperimentalCodexAuthProvider()
    status = provider.status()
    if status.authenticated:
        recommended_action = (
            "Native experimental Codex OAuth credentials are present. Select "
            "`codex_oauth_experimental` explicitly for direct execution, or use "
            "`codex_sidecar` if you prefer the local bridge path."
        )
        detail = status.detail
    else:
        recommended_action = (
            "Run `syncore auth codex login` or `syncore auth codex login --device` to create "
            "local experimental credentials, then select `codex_oauth_experimental` for "
            "direct execution or configure `codex_sidecar`."
        )
        detail = "no native experimental Codex OAuth credentials stored"
    return ExperimentalProviderDiagnostics(
        provider=status.provider,
        mode=status.mode,
        warning=(
            "Experimental native ChatGPT/Codex OAuth path. This is separate from official "
            "OpenAI Platform API-key mode and may break if the upstream Codex backend changes."
        ),
        recommended_action=recommended_action,
        provider_registered=status.authenticated,
        executable=status.authenticated,
        detail=detail,
        implementation_state=status.implementation_state,
        authenticated=status.authenticated,
        can_refresh=status.can_refresh,
        storage_secure=status.storage_secure,
        token_path=status.token_path,
        expires_at=status.expires_at,
    )


def _probe_codex_sidecar(base_url: str, api_key: str) -> tuple[bool, str]:
    candidate_paths = ("/health", "/v1/models")
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    for path in candidate_paths:
        url = f"{base_url.rstrip('/')}{path}"
        try:
            response = httpx.get(url, headers=headers, timeout=2.0)
            if response.status_code in {200, 204, 400, 401, 403, 404, 405}:
                return True, f"reachable via {path} ({response.status_code})"
            return False, f"sidecar responded with HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            detail = str(exc)
            continue
    return False, f"unreachable: {detail}" if 'detail' in locals() else "unreachable"
