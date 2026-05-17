from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.experimental_auth import CodexOAuthError, ExperimentalCodexAuthProvider
from app.services.local_auth_service import (
    LocalAuthError,
    LocalOpenAIAuthService,
    OpenAIAuthStatus,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class OpenAIStatusResponse(BaseModel):
    configured: bool
    storage_secure: bool
    token_path: str
    detail: str
    models: list[str] = Field(default_factory=list)


class OpenAILoginRequest(BaseModel):
    api_key: str = Field(min_length=1)


class OpenAILoginResponse(BaseModel):
    configured: bool
    storage_secure: bool
    token_path: str
    detail: str
    models: list[str]


class CodexStatusResponse(BaseModel):
    provider: str
    mode: str
    implementation_state: str
    authenticated: bool
    can_refresh: bool
    storage_secure: bool
    token_path: str
    expires_at: str | None = None
    detail: str
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)


class CodexLoginResponse(BaseModel):
    authenticated: bool
    storage_secure: bool
    token_path: str
    expires_at: str | None = None
    detail: str
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)


class CodexBrowserLoginStartResponse(BaseModel):
    auth_url: str
    pending: bool
    detail: str


def get_openai_auth_service() -> LocalOpenAIAuthService:
    return LocalOpenAIAuthService()


def get_codex_auth_provider() -> ExperimentalCodexAuthProvider:
    return ExperimentalCodexAuthProvider()


@router.get("/openai/status", response_model=OpenAIStatusResponse)
def openai_status(
    service: LocalOpenAIAuthService = Depends(get_openai_auth_service),
) -> OpenAIStatusResponse:
    status = service.status()
    models: list[str] = []
    if status.configured:
        try:
            models = service.list_models()
        except LocalAuthError as error:
            status = OpenAIAuthStatus(
                configured=status.configured,
                storage_secure=status.storage_secure,
                token_path=status.token_path,
                detail=f"{status.detail} Model discovery failed: {error}",
            )
    return _build_openai_status_response(status, models=models)


@router.post("/openai/login", response_model=OpenAILoginResponse)
def openai_login(
    payload: OpenAILoginRequest,
    service: LocalOpenAIAuthService = Depends(get_openai_auth_service),
) -> OpenAILoginResponse:
    try:
        models = service.save_api_key(payload.api_key)
    except LocalAuthError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    status = service.status()
    return OpenAILoginResponse(**_build_openai_status_response(status, models=models).model_dump())


@router.post("/openai/logout", response_model=OpenAIStatusResponse)
def openai_logout(
    service: LocalOpenAIAuthService = Depends(get_openai_auth_service),
) -> OpenAIStatusResponse:
    service.clear()
    return _build_openai_status_response(service.status(), models=[])


@router.get("/openai/models", response_model=list[str])
def openai_models(service: LocalOpenAIAuthService = Depends(get_openai_auth_service)) -> list[str]:
    try:
        return service.list_models()
    except LocalAuthError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/codex/status", response_model=CodexStatusResponse)
def codex_status(
    provider: ExperimentalCodexAuthProvider = Depends(get_codex_auth_provider),
) -> CodexStatusResponse:
    return CodexStatusResponse(**provider.status().__dict__)


@router.post("/codex/login/browser", response_model=CodexBrowserLoginStartResponse)
def codex_login_browser(
    provider: ExperimentalCodexAuthProvider = Depends(get_codex_auth_provider),
) -> CodexBrowserLoginStartResponse:
    try:
        auth_url = provider.start_browser_login()
    except CodexOAuthError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return CodexBrowserLoginStartResponse(
        auth_url=auth_url,
        pending=True,
        detail=(
            "Browser OAuth flow started. OpenAI authentication should complete in the new tab."
        ),
    )


@router.post("/codex/refresh", response_model=CodexLoginResponse)
def codex_refresh(
    provider: ExperimentalCodexAuthProvider = Depends(get_codex_auth_provider),
) -> CodexLoginResponse:
    try:
        provider.refresh()
    except CodexOAuthError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    status = provider.status()
    return CodexLoginResponse(
        authenticated=status.authenticated,
        storage_secure=status.storage_secure,
        token_path=status.token_path,
        expires_at=status.expires_at,
        detail=status.detail,
        metadata=status.metadata,
    )


@router.post("/codex/logout", response_model=CodexStatusResponse)
def codex_logout(
    provider: ExperimentalCodexAuthProvider = Depends(get_codex_auth_provider),
) -> CodexStatusResponse:
    provider.clear()
    return CodexStatusResponse(**provider.status().__dict__)


def _build_openai_status_response(
    status: OpenAIAuthStatus,
    *,
    models: list[str],
) -> OpenAIStatusResponse:
    return OpenAIStatusResponse(
        configured=status.configured,
        storage_secure=status.storage_secure,
        token_path=status.token_path,
        detail=status.detail,
        models=models,
    )
