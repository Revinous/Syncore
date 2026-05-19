from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services.local_settings_service import (
    KNOWN_PROVIDER_PREFERENCES,
    LocalExecutionSettingsService,
    LocalSettingsError,
)
from app.services.run_execution_service import RunExecutionService

router = APIRouter(prefix="/settings", tags=["settings"])


class RuntimeSettingsResponse(BaseModel):
    configured: bool
    storage_secure: bool
    settings_path: str
    default_provider_preference: str | None = None
    resolved_default_provider: str
    resolved_default_model: str
    detail: str
    updated_at: str | None = None
    available_provider_preferences: list[str] = Field(default_factory=list)


class RuntimeSettingsUpdateRequest(BaseModel):
    default_provider_preference: str | None = None


def _settings_status(settings: Settings) -> RuntimeSettingsResponse:
    run_service = RunExecutionService.from_settings(settings)
    capabilities = run_service.list_provider_capabilities()
    configured = {item.provider for item in capabilities}
    hints = {item.provider: item.model_hint for item in capabilities}
    status = LocalExecutionSettingsService().status(
        configured_providers=configured,
        provider_model_hints=hints,
        fallback_provider=settings.default_llm_provider,
        fallback_model=settings.autonomy_default_model,
    )
    available_preferences = [
        provider for provider in KNOWN_PROVIDER_PREFERENCES if provider in configured
    ]
    return RuntimeSettingsResponse(
        configured=status.configured,
        storage_secure=status.storage_secure,
        settings_path=status.settings_path,
        default_provider_preference=status.default_provider_preference,
        resolved_default_provider=status.resolved_default_provider,
        resolved_default_model=status.resolved_default_model,
        detail=status.detail,
        updated_at=status.updated_at,
        available_provider_preferences=available_preferences,
    )


@router.get("", response_model=RuntimeSettingsResponse)
def get_runtime_settings(
    settings: Settings = Depends(get_settings),
) -> RuntimeSettingsResponse:
    return _settings_status(settings)


@router.put("", response_model=RuntimeSettingsResponse)
def update_runtime_settings(
    payload: RuntimeSettingsUpdateRequest,
    settings: Settings = Depends(get_settings),
) -> RuntimeSettingsResponse:
    service = LocalExecutionSettingsService()
    try:
        service.save_default_provider_preference(payload.default_provider_preference)
    except LocalSettingsError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _settings_status(settings)
