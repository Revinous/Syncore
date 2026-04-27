from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CliConfig:
    api_url: str = "http://localhost:8000"
    timeout_seconds: float = 10.0


def load_config() -> CliConfig:
    api_url = os.getenv("SYNCORE_API_URL", "http://localhost:8000").rstrip("/")
    timeout_raw = os.getenv("SYNCORE_API_TIMEOUT_SECONDS", "10")
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError:
        timeout_seconds = 10.0
    return CliConfig(api_url=api_url, timeout_seconds=timeout_seconds)
