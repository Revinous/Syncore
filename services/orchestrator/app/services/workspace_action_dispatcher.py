from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID


@dataclass
class WorkspaceLoopState:
    changed_files: list[str] = field(default_factory=list)
    diff_refs: list[str] = field(default_factory=list)
    command_results: list[dict[str, object]] = field(default_factory=list)
    read_refs: list[str] = field(default_factory=list)
    completed_work: list[str] = field(default_factory=list)
    next_action: str = "Run the repo's verification checks for the changed files."
    finish_summary: str = ""


class WorkspaceActionDispatcher:
    def __init__(
        self,
        *,
        check_action_allowed,
        write_with_diff,
        patch_with_diff,
        delete_with_diff,
        move_with_diff,
        read_file,
        search_code,
        store_text_reference,
        run_workspace_command,
        runner_default_command,
    ) -> None:
        self._check_action_allowed = check_action_allowed
        self._write_with_diff = write_with_diff
        self._patch_with_diff = patch_with_diff
        self._delete_with_diff = delete_with_diff
        self._move_with_diff = move_with_diff
        self._read_file = read_file
        self._search_code = search_code
        self._store_text_reference = store_text_reference
        self._run_workspace_command = run_workspace_command
        self._runner_default_command = runner_default_command

    def dispatch_actions(
        self,
        *,
        task_id: UUID,
        root: Path,
        actions: list[dict[str, object]],
        policy: dict[str, object],
        runner: dict[str, object],
        state: WorkspaceLoopState,
    ) -> bool:
        for action in actions:
            action_type = str(action.get("type", "")).strip().lower()
            action_gate = self._check_action_allowed(
                action_type=action_type,
                policy=policy,
                relative_path=str(action.get("path", "")).strip() or None,
                command=str(action.get("command", "")).strip() or None,
            )
            if action_gate["status"] != "ok":
                state.command_results.append(
                    {
                        "command": str(action.get("command") or action_type),
                        "status": "blocked",
                        "output": str(action_gate.get("reason") or "Action blocked"),
                    }
                )
                continue
            if action_type in {"write_file", "create_file"}:
                rel = str(action.get("path", "")).strip()
                content = str(action.get("content", ""))
                if not rel:
                    continue
                ref_id = self._write_with_diff(
                    task_id=task_id,
                    root=root,
                    relative_path=rel,
                    content=content,
                )
                state.changed_files.append(rel)
                state.diff_refs.append(ref_id)
                verb = "Created" if action_type == "create_file" else "Updated"
                state.completed_work.append(f"{verb} {rel}")
            elif action_type == "patch_file":
                rel = str(action.get("path", "")).strip()
                before = str(action.get("before", ""))
                after = str(action.get("after", ""))
                if not rel or not before:
                    continue
                ref_id = self._patch_with_diff(
                    task_id=task_id,
                    root=root,
                    relative_path=rel,
                    before_text=before,
                    after_text=after,
                )
                state.changed_files.append(rel)
                state.diff_refs.append(ref_id)
                state.completed_work.append(f"Patched {rel}")
            elif action_type == "delete_file":
                rel = str(action.get("path", "")).strip()
                if not rel:
                    continue
                ref_id = self._delete_with_diff(
                    task_id=task_id,
                    root=root,
                    relative_path=rel,
                )
                state.changed_files.append(rel)
                state.diff_refs.append(ref_id)
                state.completed_work.append(f"Deleted {rel}")
            elif action_type == "move_file":
                rel = str(action.get("path", "")).strip()
                destination = str(action.get("destination", "")).strip()
                if not rel or not destination:
                    continue
                ref_id = self._move_with_diff(
                    task_id=task_id,
                    root=root,
                    source_path=rel,
                    destination_path=destination,
                )
                state.changed_files.extend([rel, destination])
                state.diff_refs.append(ref_id)
                state.completed_work.append(f"Moved {rel} to {destination}")
            elif action_type == "read_file":
                rel = str(action.get("path", "")).strip()
                if not rel:
                    continue
                read = self._read_file(root=root, relative_path=rel)
                if read:
                    state.read_refs.append(
                        self._store_text_reference(
                            task_id=task_id,
                            content_type="workspace_read",
                            content_text=read,
                            retrieval_hint=f"Read snapshot for {rel}",
                        )
                    )
            elif action_type == "search_code":
                pattern = str(action.get("pattern", "")).strip()
                if not pattern:
                    continue
                hits = self._search_code(root=root, pattern=pattern)
                if hits:
                    state.read_refs.append(
                        self._store_text_reference(
                            task_id=task_id,
                            content_type="workspace_search",
                            content_text="\n".join(hits),
                            retrieval_hint=f"Search hits for pattern '{pattern}'",
                        )
                    )
            elif action_type == "run_command":
                command = str(action.get("command", "")).strip()
                if not command:
                    continue
                state.command_results.append(
                    self._run_workspace_command(root, command, policy=policy)
                )
            elif action_type in {"run_test", "run_targeted_test"}:
                command = str(
                    action.get("command")
                    or self._runner_default_command(runner, "test", "pytest -q")
                ).strip()
                state.command_results.append(
                    self._run_workspace_command(root, command, policy=policy)
                )
            elif action_type == "run_build":
                command = str(
                    action.get("command")
                    or self._runner_default_command(runner, "build", "npm run build")
                ).strip()
                state.command_results.append(
                    self._run_workspace_command(root, command, policy=policy)
                )
            elif action_type == "run_lint":
                command = str(
                    action.get("command") or self._runner_default_command(runner, "lint", "")
                ).strip()
                if not command:
                    continue
                state.command_results.append(
                    self._run_workspace_command(root, command, policy=policy)
                )
            elif action_type == "run_format":
                command = str(
                    action.get("command") or self._runner_default_command(runner, "format", "")
                ).strip()
                if not command:
                    continue
                state.command_results.append(
                    self._run_workspace_command(root, command, policy=policy)
                )
            elif action_type == "install_deps":
                command = str(
                    action.get("command") or self._runner_default_command(runner, "setup", "")
                ).strip()
                if not command:
                    continue
                state.command_results.append(
                    self._run_workspace_command(root, command, policy=policy)
                )
            elif action_type == "complete_work":
                text = str(action.get("text", "")).strip()
                if text:
                    state.completed_work.append(text)
            elif action_type == "next_action":
                text = str(action.get("text", "")).strip()
                if text:
                    state.next_action = text
            elif action_type == "finish":
                state.finish_summary = str(action.get("summary", "")).strip() or (
                    "Workspace execution loop completed."
                )
                return True
        return False
