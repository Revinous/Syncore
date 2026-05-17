from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TokenBundle:
    provider: str
    access_token: str
    refresh_token: str | None = None
    id_token: str | None = None
    token_type: str = "Bearer"
    expires_at: str | None = None
    metadata: dict[str, str | int | bool | None] = field(default_factory=dict)


@dataclass(frozen=True)
class ExperimentalAuthStatus:
    provider: str
    mode: str
    implementation_state: str
    authenticated: bool
    can_refresh: bool
    storage_secure: bool
    token_path: str
    expires_at: str | None
    detail: str
    metadata: dict[str, str | int | bool | None] = field(default_factory=dict)
