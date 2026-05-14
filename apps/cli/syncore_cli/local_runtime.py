from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from .client import SyncoreApiError, SyncoreApiClient


def repo_root() -> Path:
    explicit = os.getenv("SYNCORE_REPO_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def ensure_api_running(*, client: SyncoreApiClient, api_url: str) -> None:
    try:
        client.health()
        return
    except SyncoreApiError:
        pass

    parsed = urlparse(api_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8000
    if host not in {"localhost", "127.0.0.1"}:
        raise SyncoreApiError(
            f"Syncore API is offline at {api_url}. Auto-start supports local URLs only."
        )

    runtime_mode = os.getenv("SYNCORE_RUNTIME_MODE", "native")
    db_backend = os.getenv("SYNCORE_DB_BACKEND", "sqlite")
    if runtime_mode != "native" or db_backend != "sqlite":
        raise SyncoreApiError(
            "Syncore API is offline and auto-start requires SYNCORE_RUNTIME_MODE=native and SYNCORE_DB_BACKEND=sqlite."
        )

    root = repo_root()
    python_bin = root / ".venv/bin/python"
    if not python_bin.exists():
        raise SyncoreApiError(f"Missing virtualenv at {python_bin}. Run `make install-local`.")

    env = os.environ.copy()
    env.setdefault("SYNCORE_RUNTIME_MODE", "native")
    env.setdefault("SYNCORE_DB_BACKEND", "sqlite")
    env.setdefault("SQLITE_DB_PATH", ".syncore/syncore.db")
    env.setdefault("REDIS_REQUIRED", "false")

    subprocess.run(
        ["bash", str(root / "scripts/init_local_sqlite.sh")],
        cwd=root,
        env=env,
        check=True,
    )

    log_dir = root / ".syncore"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "orchestrator-cli.log"

    with log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(
            [
                str(python_bin),
                "-m",
                "uvicorn",
                "app.main:app",
                "--app-dir",
                "services/orchestrator",
                "--host",
                host,
                "--port",
                str(port),
            ],
            cwd=root,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            client.health()
            return
        except SyncoreApiError:
            time.sleep(0.25)

    raise SyncoreApiError(
        f"Failed to start orchestrator at {api_url}. See logs: {log_path}"
    )


def web_url() -> str:
    return os.getenv("SYNCORE_WEB_URL", "http://localhost:3000").rstrip("/")


def ensure_web_running() -> str:
    resolved_web_url = web_url()
    parsed = urlparse(resolved_web_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 3000
    if host not in {"localhost", "127.0.0.1"}:
        raise SyncoreApiError(
            f"Syncore Web UI is configured at {resolved_web_url}. Auto-start supports local URLs only."
        )

    health_url = f"{parsed.scheme or 'http'}://{host}:{port}"
    try:
        with urlopen(health_url, timeout=1.5):
            return resolved_web_url
    except URLError:
        pass

    root = repo_root()
    next_bin = root / "apps/web/node_modules/.bin/next"
    if not next_bin.exists():
        raise SyncoreApiError(
            f"Missing Next.js dev binary at {next_bin}. Run `make install-local`."
        )

    env = os.environ.copy()
    env.setdefault("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000")
    env.setdefault("ORCHESTRATOR_INTERNAL_URL", env["NEXT_PUBLIC_API_BASE_URL"])

    log_dir = root / ".syncore"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "web-cli.log"

    with log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(
            [str(next_bin), "dev", "--port", str(port)],
            cwd=root / "apps/web",
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            with urlopen(health_url, timeout=1.5):
                return resolved_web_url
        except URLError:
            time.sleep(0.25)

    raise SyncoreApiError(
        f"Failed to start Web UI at {resolved_web_url}. See logs: {log_path}"
    )


def open_browser(url: str) -> bool:
    if os.name == "nt":
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        except OSError:
            return False

    commands: list[list[str]] = []
    if os.getenv("WSL_DISTRO_NAME"):
        if shutil.which("wslview"):
            commands.append(["wslview", url])
        if shutil.which("cmd.exe"):
            commands.append(["cmd.exe", "/c", "start", "", url])
    elif sys.platform == "darwin":
        commands.append(["open", url])
    else:
        has_display = bool(os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"))
        if has_display and shutil.which("xdg-open"):
            commands.append(["xdg-open", url])

    for command in commands:
        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except OSError:
            continue
    return False
