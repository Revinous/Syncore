from __future__ import annotations

import json
import re
from pathlib import Path


class WorkspacePlanner:
    def build_worker_prompt(
        self,
        *,
        base_prompt: str,
        file_snapshot: str,
        working_memory: str,
        step: int,
        max_steps: int,
        contract: dict[str, object],
        runner: dict[str, object],
        policy: dict[str, object],
    ) -> str:
        return (
            "You are Syncore workspace coder.\n"
            f"Step {step}/{max_steps}.\n"
            "You are not being asked to execute tools yourself.\n"
            "Your only job is to return the NEXT file mutations or commands as JSON actions.\n"
            "Do not say that tools are unavailable. "
            "Do not describe limitations. Emit actions only.\n"
            "If you need file contents, request them with read_file actions.\n"
            "If you need to create implementation files, use create_file or write_file actions.\n"
            "Return ONLY JSON with schema: "
            '{"actions":[{"type":"read_file|search_code|write_file|create_file|patch_file|move_file|delete_file|run_command|run_test|run_build|run_lint|run_format|run_targeted_test|install_deps|complete_work|next_action|finish",'
            '"path":"...","destination":"...","content":"...","before":"...","after":"...","pattern":"...","command":"...","text":"...","summary":"..."}]}\n'
            "Prefer write_file with full file content for deterministic updates.\n"
            "Use commands only when needed for verification.\n\n"
            "Task:\n"
            f"{base_prompt}\n\n"
            "Workspace contract:\n"
            f"{contract}\n\n"
            "Selected runner:\n"
            f"{runner}\n\n"
            "Execution policy:\n"
            f"{policy}\n\n"
            "Workspace snapshot:\n"
            f"{file_snapshot}\n\n"
            "Read/search context from previous steps:\n"
            f"{working_memory or '(none yet)'}"
        )

    def build_worker_repair_prompt(
        self,
        *,
        prior_output: str,
    ) -> str:
        return (
            "Your previous answer did not follow the required JSON action schema.\n"
            "You DO have access to workspace operations by returning action objects.\n"
            "Do not explain. Do not apologize. Do not mention tools or limitations.\n"
            "Return ONLY valid JSON in the form "
            '{"actions":[...]}'
            " with at least one concrete next action.\n\n"
            "Previous invalid answer:\n"
            f"{prior_output[:4000]}"
        )

    def build_planner_prompt(
        self,
        *,
        base_prompt: str,
        workspace_runbook: object,
        profile: str,
    ) -> str:
        return (
            "You are planning safe workspace actions for an autonomous coding loop.\n"
            f"Policy profile: {profile}.\n"
            "Return concise numbered steps, no markdown table.\n"
            "Prefer test/build verification and minimal file mutations.\n\n"
            f"Task:\n{base_prompt}\n\n"
            f"Workspace runbook metadata:\n{workspace_runbook}\n"
        )

    def parse_plan_lines(self, output_text: str) -> list[str]:
        lines = [line.strip(" -\t") for line in output_text.splitlines() if line.strip()]
        return [line[:240] for line in lines[:60]]

    def workspace_snapshot(self, root: Path) -> str:
        entries: list[str] = []
        for path in root.rglob("*"):
            if len(entries) >= 200:
                break
            if path.is_dir():
                continue
            rel_parts = path.relative_to(root).parts
            blocked_parts = {".git", "node_modules", ".venv", "__pycache__", ".next"}
            if any(part in blocked_parts for part in rel_parts):
                continue
            entries.append(path.relative_to(root).as_posix())
        if not entries:
            return "(empty workspace)"
        return "\n".join(f"- {item}" for item in entries)

    def parse_worker_actions(self, output_text: str) -> list[dict[str, object]]:
        candidate = output_text.strip()
        fenced = re.search(r"```json\s*(\{.*?\})\s*```", candidate, re.DOTALL)
        if fenced:
            candidate = fenced.group(1)
        payload = self._parse_json_object(candidate)
        if payload is None:
            return []
        actions = payload.get("actions", [])
        if not isinstance(actions, list):
            return []
        return [action for action in actions if isinstance(action, dict)]

    def _parse_json_object(self, text: str) -> dict[str, object] | None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return payload

        match = re.search(r"(\{[\s\S]*\"actions\"\s*:\s*\[[\s\S]*\]\s*\})", text)
        if not match:
            return None
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None
