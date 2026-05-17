from __future__ import annotations

import base64
import binascii
import json
import time
import webbrowser
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from .models import TokenBundle
from .pkce import PKCECodes, generate_pkce_codes, generate_state

AUTH_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
DEVICE_USER_CODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
DEVICE_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
DEVICE_VERIFICATION_URL = "https://auth.openai.com/codex/device"
DEVICE_REDIRECT_URI = "https://auth.openai.com/deviceauth/callback"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
DEFAULT_CALLBACK_PORT = 1455
DEFAULT_TIMEOUT_SECONDS = 30.0
DEVICE_TIMEOUT_SECONDS = 15 * 60


class CodexOAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeviceCodeResponse:
    device_auth_id: str
    user_code: str
    interval_seconds: int


class CodexAuthHttpClient:
    def __init__(self, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds

    def generate_auth_url(self, state: str, pkce: PKCECodes, callback_port: int) -> str:
        redirect_uri = _redirect_uri(callback_port)
        params = {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": "openid email profile offline_access",
            "state": state,
            "code_challenge": pkce.code_challenge,
            "code_challenge_method": "S256",
            "prompt": "login",
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_tokens(
        self, code: str, pkce: PKCECodes, callback_port: int
    ) -> TokenBundle:
        redirect_uri = _redirect_uri(callback_port)
        response = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": pkce.code_verifier,
            },
            headers={"Accept": "application/json"},
            timeout=self._timeout_seconds,
        )
        return self._parse_token_response(response)

    def exchange_device_code_for_tokens(
        self, authorization_code: str, pkce: PKCECodes
    ) -> TokenBundle:
        response = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": authorization_code,
                "redirect_uri": DEVICE_REDIRECT_URI,
                "code_verifier": pkce.code_verifier,
            },
            headers={"Accept": "application/json"},
            timeout=self._timeout_seconds,
        )
        return self._parse_token_response(response)

    def refresh_tokens(self, refresh_token: str) -> TokenBundle:
        response = httpx.post(
            TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": "openid profile email",
            },
            headers={"Accept": "application/json"},
            timeout=self._timeout_seconds,
        )
        return self._parse_token_response(response)

    def request_device_code(self) -> DeviceCodeResponse:
        response = httpx.post(
            DEVICE_USER_CODE_URL,
            json={"client_id": CLIENT_ID},
            headers={"Accept": "application/json"},
            timeout=self._timeout_seconds,
        )
        payload = self._expect_json(response, operation="request device code")
        device_auth_id = str(payload.get("device_auth_id", "")).strip()
        user_code = str(payload.get("user_code") or payload.get("usercode") or "").strip()
        if not device_auth_id or not user_code:
            raise CodexOAuthError("Codex device flow did not return required fields.")
        interval_raw = payload.get("interval", 5)
        try:
            interval_seconds = max(int(interval_raw), 1)
        except (TypeError, ValueError):
            interval_seconds = 5
        return DeviceCodeResponse(
            device_auth_id=device_auth_id,
            user_code=user_code,
            interval_seconds=interval_seconds,
        )

    def poll_device_authorization(
        self, device_auth_id: str, user_code: str, interval_seconds: int
    ) -> tuple[str, PKCECodes]:
        deadline = time.time() + DEVICE_TIMEOUT_SECONDS
        while time.time() < deadline:
            response = httpx.post(
                DEVICE_TOKEN_URL,
                json={
                    "device_auth_id": device_auth_id,
                    "user_code": user_code,
                },
                headers={"Accept": "application/json"},
                timeout=self._timeout_seconds,
            )
            if response.status_code in {403, 404}:
                time.sleep(interval_seconds)
                continue
            payload = self._expect_json(response, operation="poll device authorization")
            authorization_code = str(payload.get("authorization_code", "")).strip()
            code_verifier = str(payload.get("code_verifier", "")).strip()
            code_challenge = str(payload.get("code_challenge", "")).strip()
            if not authorization_code or not code_verifier or not code_challenge:
                raise CodexOAuthError("Codex device flow token response missing required fields.")
            return authorization_code, PKCECodes(
                code_verifier=code_verifier,
                code_challenge=code_challenge,
            )
        raise CodexOAuthError("Codex device authentication timed out after 15 minutes.")

    def _parse_token_response(self, response: httpx.Response) -> TokenBundle:
        payload = self._expect_json(response, operation="token exchange")
        access_token = str(payload.get("access_token", "")).strip()
        if not access_token:
            raise CodexOAuthError("Codex token response did not include an access token.")
        refresh_token = _optional_string(payload.get("refresh_token"))
        id_token = _optional_string(payload.get("id_token"))
        expires_in = int(payload.get("expires_in") or 0)
        expires_at = None
        if expires_in > 0:
            expires_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + expires_in))
        metadata = _extract_id_token_metadata(id_token)
        return TokenBundle(
            provider="codex_oauth_experimental",
            access_token=access_token,
            refresh_token=refresh_token,
            id_token=id_token,
            token_type=_optional_string(payload.get("token_type")) or "Bearer",
            expires_at=expires_at,
            metadata=metadata,
        )

    def _expect_json(self, response: httpx.Response, *, operation: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise CodexOAuthError(f"Codex {operation} returned non-JSON output.") from error
        if response.status_code >= 400:
            raise CodexOAuthError(
                f"Codex {operation} failed with status {response.status_code}: {payload}"
            )
        if not isinstance(payload, dict):
            raise CodexOAuthError(f"Codex {operation} returned an unexpected payload shape.")
        return payload


def open_browser(url: str) -> bool:
    try:
        return webbrowser.open(url)
    except (webbrowser.Error, OSError):
        return False


def build_browser_login_state(
    callback_port: int = DEFAULT_CALLBACK_PORT,
) -> tuple[str, PKCECodes, str]:
    state = generate_state()
    pkce = generate_pkce_codes()
    client = CodexAuthHttpClient()
    return state, pkce, client.generate_auth_url(state, pkce, callback_port)


def _redirect_uri(callback_port: int) -> str:
    return f"http://localhost:{callback_port}/auth/callback"


def _optional_string(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _extract_id_token_metadata(id_token: str | None) -> dict[str, str | int | bool | None]:
    if not id_token:
        return {}
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return {}
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return {}
    metadata: dict[str, str | int | bool | None] = {}
    if isinstance(payload, dict):
        metadata["email"] = _optional_string(payload.get("email"))
        codex_info = payload.get("https://api.openai.com/auth")
        if isinstance(codex_info, dict):
            metadata["chatgpt_plan_type"] = _optional_string(codex_info.get("chatgpt_plan_type"))
            metadata["chatgpt_account_id"] = _optional_string(codex_info.get("chatgpt_account_id"))
    return metadata
