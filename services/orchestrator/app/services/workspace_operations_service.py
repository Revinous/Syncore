from __future__ import annotations

import shutil
import subprocess
from difflib import unified_diff
from pathlib import Path
from textwrap import shorten
from uuid import UUID

from app.context.retrieval_refs import build_ref_id
from app.services.workspace_execution_utils import (
    command_allowed,
    needs_dependency_bootstrap,
    normalize_workspace_command,
    resolve_workspace_path,
    runner_default_command,
)
from app.services.workspace_files import WorkspaceFilesService


class WorkspaceOperationsService:
    def __init__(self, *, store, record_event, binary_available) -> None:
        self._store = store
        self._record_event = record_event
        self._binary_available = binary_available

    def write_with_diff(
        self,
        *,
        task_id: UUID,
        root: Path,
        relative_path: str,
        content: str,
    ) -> str:
        target = resolve_workspace_path(root, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        before = ""
        if target.exists():
            before = target.read_text(encoding="utf-8", errors="replace")
        target.write_text(content, encoding="utf-8")
        after = target.read_text(encoding="utf-8", errors="replace")
        diff = "".join(
            unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
            )
        )
        if not diff.strip():
            diff = f"(no textual diff) {relative_path}"
        ref = self._store.upsert_context_reference(
            ref_id=build_ref_id(task_id, "workspace_diff", diff),
            task_id=task_id,
            content_type="workspace_diff",
            original_content=diff,
            summary=shorten(" ".join(diff.split()), width=220, placeholder=" ..."),
            retrieval_hint=f"Diff for workspace file {relative_path}",
        )
        ref_id = str(ref["ref_id"])
        self._record_event(
            task_id=task_id,
            event_type="artifact.diff.stored",
            event_data={"path": relative_path, "ref_id": ref_id},
        )
        return ref_id

    def patch_with_diff(
        self,
        *,
        task_id: UUID,
        root: Path,
        relative_path: str,
        before_text: str,
        after_text: str,
    ) -> str:
        target = resolve_workspace_path(root, relative_path)
        if not target.exists():
            raise FileNotFoundError(f"Patch target does not exist: {relative_path}")
        existing = target.read_text(encoding="utf-8", errors="replace")
        if before_text not in existing:
            raise ValueError(f"Patch before-text not found in {relative_path}")
        updated = existing.replace(before_text, after_text, 1)
        return self.write_with_diff(
            task_id=task_id,
            root=root,
            relative_path=relative_path,
            content=updated,
        )

    def delete_with_diff(
        self,
        *,
        task_id: UUID,
        root: Path,
        relative_path: str,
    ) -> str:
        target = resolve_workspace_path(root, relative_path)
        if not target.exists():
            raise FileNotFoundError(f"Delete target does not exist: {relative_path}")
        before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        if target.is_file():
            target.unlink()
        diff = "".join(
            unified_diff(
                before.splitlines(keepends=True),
                [],
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
            )
        )
        ref = self._store.upsert_context_reference(
            ref_id=build_ref_id(task_id, "workspace_diff", diff or relative_path),
            task_id=task_id,
            content_type="workspace_diff",
            original_content=diff or f"Deleted {relative_path}",
            summary=shorten(
                " ".join((diff or f"Deleted {relative_path}").split()),
                width=220,
                placeholder=" ...",
            ),
            retrieval_hint=f"Diff for workspace file {relative_path}",
        )
        ref_id = str(ref["ref_id"])
        self._record_event(
            task_id=task_id,
            event_type="artifact.diff.stored",
            event_data={"path": relative_path, "ref_id": ref_id},
        )
        return ref_id

    def move_with_diff(
        self,
        *,
        task_id: UUID,
        root: Path,
        source_path: str,
        destination_path: str,
    ) -> str:
        source = resolve_workspace_path(root, source_path)
        destination = resolve_workspace_path(root, destination_path)
        if not source.exists():
            raise FileNotFoundError(f"Move source does not exist: {source_path}")
        before = source.read_text(encoding="utf-8", errors="replace") if source.is_file() else ""
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        diff = (
            f"Moved {source_path} -> {destination_path}\n"
            f"Original content preview:\n{before[:1000]}"
        )
        ref = self._store.upsert_context_reference(
            ref_id=build_ref_id(task_id, "workspace_diff", diff),
            task_id=task_id,
            content_type="workspace_diff",
            original_content=diff,
            summary=shorten(" ".join(diff.split()), width=220, placeholder=" ..."),
            retrieval_hint=f"Move record for {source_path} to {destination_path}",
        )
        ref_id = str(ref["ref_id"])
        self._record_event(
            task_id=task_id,
            event_type="artifact.diff.stored",
            event_data={"path": destination_path, "ref_id": ref_id},
        )
        return ref_id

    def run_workspace_command(
        self,
        root: Path,
        command: str,
        *,
        policy: dict[str, object],
    ) -> dict[str, object]:
        if not command_allowed(command, policy):
            return {"command": command, "status": "blocked", "output": "Command not allowed"}
        command = normalize_workspace_command(command)
        if (
            command.startswith("python ")
            and shutil.which("python") is None
            and self._binary_available("python3")
        ):
            command = command.replace("python ", "python3 ", 1)
        timeout = int(policy.get("timeout_seconds", 120))
        max_output = int(policy.get("max_output_chars", 4000))
        completed = subprocess.run(
            ["/bin/bash", "-lc", command],  # nosec B603
            cwd=root,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        output = (completed.stdout or "") + (("\n" + completed.stderr) if completed.stderr else "")
        return {
            "command": command,
            "status": "ok" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode,
            "output": output[:max_output],
        }

    def read_file(self, *, root: Path, relative_path: str) -> str:
        return WorkspaceFilesService().read_file(str(root), relative_path)

    def search_code(self, *, root: Path, pattern: str) -> list[str]:
        service = WorkspaceFilesService()
        files = service.list_files(str(root), ".", limit=500)
        hits: list[str] = []
        lowered_pattern = pattern.lower()
        for rel in files:
            try:
                content = service.read_file(str(root), rel)
            except (FileNotFoundError, PermissionError, ValueError):
                continue
            for line_no, line in enumerate(content.splitlines(), start=1):
                if lowered_pattern in line.lower():
                    hits.append(f"{rel}:{line_no}: {line[:240]}")
                    if len(hits) >= 100:
                        return hits
        return hits

    def attempt_auto_repair(
        self,
        *,
        task_id: UUID,
        root: Path,
        runner: dict[str, object],
        runbook: dict[str, object],
        policy: dict[str, object],
    ) -> bool:
        if not needs_dependency_bootstrap(root=root, runner=runner, runbook=runbook):
            return False
        setup_command = runner_default_command(runner, "setup", "")
        if not setup_command:
            return False
        result = self.run_workspace_command(root, setup_command, policy=policy)
        self._record_event(
            task_id=task_id,
            event_type="workspace.auto_repair.attempted",
            event_data={
                "command": setup_command[:200],
                "status": str(result.get("status") or ""),
            },
        )
        return str(result.get("status")) == "ok"
