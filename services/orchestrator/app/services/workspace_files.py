from __future__ import annotations

import fnmatch
from pathlib import Path

IGNORED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "dist",
    "build",
    ".next",
    "__pycache__",
    "target",
    "vendor",
}

BLOCKED_FILE_PATTERNS = (
    ".env",
    ".env.*",
    "id_rsa",
    "id_dsa",
    "*.pem",
    "*.key",
    "secrets.*",
    "credentials.*",
)


class WorkspaceFilesService:
    def __init__(self, max_file_size_bytes: int = 1_000_000) -> None:
        self._max_file_size_bytes = max_file_size_bytes

    def list_files(self, root_path: str, relative_path: str = ".", limit: int = 500) -> list[str]:
        root = Path(root_path).resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Workspace root not found: {root}")

        target = self._resolve_within_root(root, relative_path)
        if not target.exists() or not target.is_dir():
            raise FileNotFoundError(f"Workspace path not found: {relative_path}")

        files: list[str] = []
        for entry in target.rglob("*"):
            if entry.is_dir():
                continue
            rel = entry.relative_to(root)
            if any(part in IGNORED_DIRS for part in rel.parts):
                continue
            if self._is_blocked(rel):
                continue
            try:
                if entry.stat().st_size > self._max_file_size_bytes:
                    continue
            except OSError:
                continue
            files.append(rel.as_posix())
            if len(files) >= limit:
                break

        files.sort()
        return files

    def read_file(self, root_path: str, relative_path: str) -> str:
        root = Path(root_path).resolve()
        target = self._resolve_within_root(root, relative_path)

        rel = target.relative_to(root)
        if self._is_blocked(rel):
            raise PermissionError(f"Access denied to file: {relative_path}")

        if any(part in IGNORED_DIRS for part in rel.parts):
            raise PermissionError(f"Access denied to path: {relative_path}")

        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"File not found: {relative_path}")

        if target.stat().st_size > self._max_file_size_bytes:
            raise ValueError(f"File exceeds max size {self._max_file_size_bytes} bytes")

        return target.read_text(encoding="utf-8", errors="replace")

    def _resolve_within_root(self, root: Path, relative_path: str) -> Path:
        target = (root / relative_path).resolve()
        if root != target and root not in target.parents:
            raise PermissionError(f"Path traversal blocked: {relative_path}")
        return target

    def _is_blocked(self, relative_path: Path) -> bool:
        filename = relative_path.name
        for pattern in BLOCKED_FILE_PATTERNS:
            if fnmatch.fnmatch(filename, pattern):
                return True
            if fnmatch.fnmatch(relative_path.as_posix(), pattern):
                return True
        return False
