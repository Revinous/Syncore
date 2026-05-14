from __future__ import annotations

from pathlib import Path


class WorkspaceRiskService:
    def verify_diff_risk(
        self,
        *,
        changed_files: list[str],
        forbidden_paths: list[str],
        risk_rules: dict[str, object],
    ) -> dict[str, object]:
        if forbidden_paths:
            violations = [
                path
                for path in changed_files
                if any(
                    path == forbidden or path.startswith(forbidden.rstrip("/") + "/")
                    for forbidden in forbidden_paths
                )
            ]
            if violations:
                return {
                    "status": "failed",
                    "reason": "Workspace changed forbidden paths.",
                    "violations": violations[:20],
                }
        max_changed = risk_rules.get("max_changed_files")
        if (
            isinstance(max_changed, int)
            and max_changed > 0
            and len(set(changed_files)) > max_changed
        ):
            return {
                "status": "failed",
                "reason": "Workspace changed too many files for current risk budget.",
                "changed_files": len(set(changed_files)),
                "limit": max_changed,
            }
        return {"status": "ok", "reason": ""}

    def verify_secret_safety(self, *, root: Path, changed_files: list[str]) -> dict[str, object]:
        secret_markers = ("api_key", "secret_key", "sk-proj-", "BEGIN PRIVATE KEY")
        for rel in changed_files[:50]:
            target = root / rel
            if not target.exists() or not target.is_file():
                continue
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lowered = content.lower()
            if any(marker.lower() in lowered for marker in secret_markers):
                return {
                    "status": "failed",
                    "reason": "Potential secret material detected in changed files.",
                    "path": rel,
                }
        return {"status": "ok", "reason": ""}
