from __future__ import annotations


def latest_model_switch(events: list[dict[str, object]]) -> dict[str, object] | None:
    for event in reversed(events):
        if str(event.get("event_type")) != "model.switch.completed":
            continue
        event_data = event.get("event_data")
        if isinstance(event_data, dict):
            return event_data
    return None


def truncate_text(value: object, limit: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def task_detail_lines(
    task: dict[str, object],
    events: list[dict[str, object]],
    baton: dict[str, object] | None,
    digest: dict[str, object] | None,
    execution_report: dict[str, object] | None,
) -> list[str]:
    task_payload = task.get("task", task) if isinstance(task, dict) else {}
    if not isinstance(task_payload, dict):
        task_payload = {}
    lines = [
        f"Task: {task_payload.get('title', '-')}",
        f"ID: {task_payload.get('id', '-')}",
        f"Status: {task_payload.get('status', '-')}",
        f"Type: {task_payload.get('task_type', '-')}",
        f"Complexity: {task_payload.get('complexity', '-')}",
        f"Workspace: {task_payload.get('workspace_id') or '-'}",
        "",
        f"Recent events: {len(events)}",
    ]
    if baton:
        lines.append(f"Latest baton: {baton.get('summary', baton.get('id', '-'))}")
    if digest:
        lines.append(f"Digest: {truncate_text(digest.get('headline') or digest.get('summary', '-'))}")
    if execution_report:
        changed_files = execution_report.get("changed_files") or []
        verification_commands = execution_report.get("verification_commands") or []
        lines.extend(
            [
                "",
                "Execution outcome:",
                f"- outcome: {execution_report.get('outcome', '-')}",
                f"- meaningful_change: {execution_report.get('meaningful_change', '-')}",
                f"- verification: {execution_report.get('verification_status', '-')}",
                f"- reason: {truncate_text(execution_report.get('summary_reason', '-'))}",
                f"- changed files: {len(changed_files)}",
                f"- verification commands: {len(verification_commands)}",
            ]
        )
        for path in list(changed_files)[:5]:
            lines.append(f"  • {path}")
    return lines


def run_result_lines(result: dict[str, object]) -> list[str]:
    output_text = truncate_text(result.get("output_text"), 500)
    return [
        f"Run ID: {result.get('run_id', '-')}",
        f"Task ID: {result.get('task_id', '-')}",
        f"Status: {result.get('status', '-')}",
        f"Prompt ref: {result.get('prompt_ref_id') or '-'}",
        f"Context ref: {result.get('context_ref_id') or '-'}",
        f"Output ref: {result.get('output_ref_id') or '-'}",
        f"Retrieval hint: {result.get('retrieval_hint') or '-'}",
        "",
        f"Summary: {truncate_text(result.get('output_summary', '-'))}",
        "",
        "Output preview:",
        output_text or "(no output text)",
    ]
