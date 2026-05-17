from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class PKCECodes:
    code_verifier: str
    code_challenge: str


def generate_pkce_codes() -> PKCECodes:
    verifier = _base64url(secrets.token_bytes(32))
    challenge = _base64url(hashlib.sha256(verifier.encode("utf-8")).digest())
    return PKCECodes(code_verifier=verifier, code_challenge=challenge)


def generate_state() -> str:
    return _base64url(secrets.token_bytes(24))


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")
