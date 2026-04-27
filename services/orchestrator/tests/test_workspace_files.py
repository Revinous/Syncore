from __future__ import annotations

import pytest

from app.services.workspace_files import WorkspaceFilesService


def test_workspace_files_blocks_path_traversal(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("demo", encoding="utf-8")

    service = WorkspaceFilesService()
    with pytest.raises(PermissionError):
        service.list_files(str(root), "../")


def test_workspace_files_blocks_secret_patterns(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("demo", encoding="utf-8")
    (root / ".env").write_text("SECRET=1", encoding="utf-8")
    (root / "credentials.json").write_text("{}", encoding="utf-8")

    service = WorkspaceFilesService()
    files = service.list_files(str(root))

    assert "README.md" in files
    assert ".env" not in files
    assert "credentials.json" not in files

    with pytest.raises(PermissionError):
        service.read_file(str(root), ".env")
