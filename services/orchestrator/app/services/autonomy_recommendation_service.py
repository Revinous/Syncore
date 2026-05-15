from __future__ import annotations

from pathlib import Path
from textwrap import shorten
from uuid import uuid4

from packages.contracts.python.models import Task


class AutonomyRecommendationService:
    def __init__(
        self,
        *,
        store,
        candidate_state,
        parse_uuid,
        extract_first_match,
        extract_paths,
        extract_list_items,
        string_list,
    ) -> None:
        self._store = store
        self._candidate_state = candidate_state
        self._parse_uuid = parse_uuid
        self._extract_first_match = extract_first_match
        self._extract_paths = extract_paths
        self._extract_list_items = extract_list_items
        self._string_list = string_list

    def selected_candidate_prompt_context(self, *, task: Task, prefs: dict[str, str]) -> str:
        return self._candidate_state.selected_candidate_prompt_context(task=task, prefs=prefs)

    def recommended_improvement_prompt_context(self, *, task: Task, prefs: dict[str, str]) -> str:
        return self.selected_candidate_prompt_context(task=task, prefs=prefs)

    def selected_candidate_state(self, parent_id) -> dict[str, object]:
        return self._candidate_state.selected_candidate_state(parent_id)

    def recommended_improvement_state(self, parent_id) -> dict[str, object]:
        return self._candidate_state.recommended_improvement_state(parent_id)

    def extract_recommended_improvement(self, output_text: str) -> dict[str, object]:
        text = (output_text or "").strip()
        summary = self._extract_first_match(
            text,
            [
                r"(?im)^(?:candidate improvement|recommended improvement|improvement)\s*:\s*(.+)$",
                r"(?im)^(?:summary|change summary)\s*:\s*(.+)$",
            ],
        )
        action = self._extract_first_match(
            text,
            [
                r"(?im)^(?:next best action|required implementation|implementation)\s*:\s*(.+)$",
                r"(?im)^(?:action|do this)\s*:\s*(.+)$",
            ],
        )
        verification = self._extract_first_match(
            text,
            [r"(?im)^(?:verification command|verify(?: with)?|test command)\s*:\s*(.+)$"],
        )
        target_files = self._extract_paths(text)
        risks = self._extract_list_items(text, headers=("risk", "risks", "constraints"))
        if not summary:
            summary = shorten(" ".join(text.split()), width=220, placeholder=" ...")
        if not action:
            action = summary
        return {
            "summary": summary.strip(),
            "action": action.strip(),
            "verification": verification.strip(),
            "target_files": target_files,
            "risks": risks,
        }

    def build_candidate_artifact(
        self,
        *,
        task: Task,
        recommendation: dict[str, object],
    ) -> dict[str, object]:
        summary = str(recommendation.get("summary") or "").strip().lower()
        target_files = self._string_list(recommendation.get("target_files"))
        verification = str(recommendation.get("verification") or "").strip()
        candidate_type = "config_contract"
        if any(path.endswith((".py", ".ts", ".tsx", ".js", ".rs", ".go")) for path in target_files):
            candidate_type = "code_fix"
        elif any("test" in path.lower() for path in target_files):
            candidate_type = "test_hardening"
        elif any("readme" in path.lower() or path.endswith(".md") for path in target_files):
            candidate_type = "docs"
        if "syncore.yaml" in summary:
            candidate_type = "config_contract"
        evidence_kind = "repo_scan+verification" if verification else "repo_scan"
        impact = 3 if candidate_type in {"code_fix", "test_hardening"} else 2
        effort = 1 if len(target_files) <= 2 else 2
        confidence = 4 if verification else 3
        risk_level = "medium" if candidate_type == "code_fix" else "low"
        return {
            "candidate_id": uuid4(),
            "candidate_type": candidate_type,
            "confidence": confidence,
            "impact": impact,
            "effort": effort,
            "risk_level": risk_level,
            "evidence_kind": evidence_kind,
            "task_type": task.task_type,
        }

    def recommendation_needs_workspace_fallback(self, recommendation: dict[str, object]) -> bool:
        text = " ".join(
            [
                str(recommendation.get("summary") or ""),
                str(recommendation.get("action") or ""),
            ]
        ).lower()
        generic_markers = (
            "don't yet have repository contents",
            "do not have repository contents",
            "please provide",
            "need more context",
            "artifact/context reference",
        )
        return any(marker in text for marker in generic_markers)

    def fallback_recommended_improvement(
        self,
        task: Task,
        recommendation: dict[str, object],
    ) -> dict[str, object]:
        if task.workspace_id is None:
            return recommendation
        workspace = self._store.get_workspace(task.workspace_id)
        if workspace is None:
            return recommendation
        metadata = dict(workspace.metadata or {})
        runbook = dict(metadata.get("workspace_runbook") or {})
        root = Path(workspace.root_path).resolve()
        verification = (
            self._string_list(runbook.get("test_commands"))[:1]
            or self._string_list(runbook.get("runbook_commands"))[:1]
        )
        verify_cmd = verification[0] if verification else ""
        syncore_contract = root / "syncore.yaml"
        if not syncore_contract.exists():
            return {
                "summary": "Add a repo-specific syncore.yaml contract for this repository.",
                "action": (
                    "Create syncore.yaml with the detected test, build, and lint commands so "
                    "future Syncore runs can inspect and verify this repo deterministically."
                ),
                "verification": verify_cmd,
                "target_files": ["syncore.yaml"],
                "risks": ["Keep the contract additive and match real repo commands exactly."],
            }
        return {
            "summary": (
                "Tighten the existing syncore.yaml contract using the current workspace scan."
            ),
            "action": (
                "Update syncore.yaml so the recorded commands and important files match the repo's "
                "actual test and verification flow."
            ),
            "verification": verify_cmd,
            "target_files": ["syncore.yaml"],
            "risks": ["Keep edits limited to syncore.yaml and preserve working repo commands."],
        }

    def workspace_analysis_prompt_context(self, task: Task) -> str:
        if task.task_type != "analysis" or task.workspace_id is None:
            return ""
        workspace = self._store.get_workspace(task.workspace_id)
        if workspace is None:
            return ""
        metadata = dict(workspace.metadata or {})
        runbook = dict(metadata.get("workspace_runbook") or {})
        root = Path(workspace.root_path).resolve()
        summary_lines = ["Workspace scan summary:"]
        for label, key in [
            ("Languages", "languages"),
            ("Frameworks", "frameworks"),
            ("Package managers", "package_managers"),
            ("Important files", "important_files"),
            ("Docs", "docs"),
        ]:
            values = self._string_list(metadata.get(key))
            if values:
                summary_lines.append(f"- {label}: {', '.join(values[:8])}")
        test_commands = self._string_list(runbook.get("test_commands"))
        if test_commands:
            summary_lines.append(f"- Test commands: {', '.join(test_commands[:4])}")
        root_files = self._workspace_root_files(root)
        if root_files:
            summary_lines.append(f"- Root files: {', '.join(root_files[:12])}")
        previews = self._workspace_file_previews(root, root_files)
        if previews:
            summary_lines.append("Key file previews:")
            summary_lines.extend(previews)
        if not (root / "syncore.yaml").exists():
            summary_lines.append("- syncore.yaml is currently missing from the repo root.")
        return "\n".join(summary_lines)

    def _workspace_root_files(self, root: Path) -> list[str]:
        try:
            items = sorted(path.name for path in root.iterdir() if path.is_file())
        except OSError:
            return []
        return items[:20]

    def _workspace_file_previews(self, root: Path, root_files: list[str]) -> list[str]:
        preview_targets = [
            "README.md",
            "pyproject.toml",
            "package.json",
            "requirements.txt",
            "setup.cfg",
            "Cargo.toml",
            "go.mod",
        ]
        previews: list[str] = []
        for name in preview_targets:
            if name not in root_files:
                continue
            path = root / name
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            compact = shorten(" ".join(text.split()), width=220, placeholder=" ...")
            previews.append(f"- {name}: {compact}")
        return previews[:6]
