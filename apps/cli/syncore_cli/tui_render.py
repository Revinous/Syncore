from __future__ import annotations

from typing import Any

def render_left_pane(app: Any) -> str:
    if app.current_view == "dashboard":
        return app._render_dashboard_left()
    if app.current_view == "workspaces":
        return app._render_workspaces_left()
    if app.current_view == "tasks":
        return app._render_tasks_left()
    if app.current_view == "task_detail":
        return app._render_task_detail_left()
    if app.current_view == "runs":
        return app._render_runs_left()
    if app.current_view == "diagnostics":
        return app._render_diagnostics_left()
    if app.current_view == "notifications":
        return app._render_notifications_left()
    if app.current_view == "metrics":
        return app._render_metrics_left()
    return "Unknown view"

def render_center_pane(app: Any) -> str:
    if app.current_view == "dashboard":
        return app._render_dashboard_center()
    if app.current_view == "workspaces":
        return app._render_workspaces_center()
    if app.current_view == "tasks":
        return app._render_tasks_center()
    if app.current_view == "task_detail":
        return app._render_task_detail_center()
    if app.current_view == "runs":
        return app._render_runs_center()
    if app.current_view == "diagnostics":
        return app._render_diagnostics_center()
    if app.current_view == "notifications":
        return app._render_notifications_center()
    if app.current_view == "metrics":
        return app._render_metrics_center()
    return ""

def render_right_pane(app: Any) -> str:
    actions_hint = "Actions: n s g o p e"
    if app.current_view == "task_detail":
        actions_hint = "Actions: s g o p e y u"
    elif app.current_view == "runs":
        actions_hint = "Actions: g o p e"
    elif app.current_view == "diagnostics":
        actions_hint = "Actions: m i"
    elif app.current_view == "notifications":
        actions_hint = "Actions: h=ack"

    lines = [
        f"API: {app._config.api_url}",
        f"Runtime: {app._summary.get('runtime_mode')}",
        f"Health: {app._summary.get('health')}",
        f"Workspace: {app._selected_workspace_name or 'none'}",
        f"Task: {app._selected_task_title or 'none'}",
        f"Unread notifications: {len(app._notifications)}",
        "",
        "Views: d/w/t/a/x/c/f | detail: v/b",
        "Nav: j/k | Refresh: r | Quit: q",
        actions_hint,
        "OpenAI: i=signin m=models",
        (f"Autonomy: {'ON' if app._autonomy_enabled else 'OFF'} (z=toggle)"),
    ]
    if app._autonomy_enabled:
        lines.append(
            f"Autonomy last scan processed: {app._last_autonomy_processed}"
        )
    if app._task_preferences:
        lines.extend(
            [
                "",
                "Task prefs:",
                f"provider={app._task_preferences.get('preferred_provider', '-')}",
                f"model={app._task_preferences.get('preferred_model', '-')}",
                f"agent={app._task_preferences.get('preferred_agent_role', '-')}",
                f"requires_approval={app._task_preferences.get('requires_approval', '-')}",
                f"sdlc_enforce={app._task_preferences.get('sdlc_enforce', '-')}",
            ]
        )
    if app._latest_model_switch:
        lines.extend(
            [
                "",
                "Latest model switch:",
                (
                    f"{app._latest_model_switch.get('from_provider', '-')}/"
                    f"{app._latest_model_switch.get('from_model', '-')} -> "
                    f"{app._latest_model_switch.get('to_provider', '-')}/"
                    f"{app._latest_model_switch.get('to_model', '-')}"
                ),
                f"bundle={app._latest_model_switch.get('context_bundle_id', '-')}",
                f"continuity={app._latest_model_switch.get('continuity_status', '-')}",
            ]
        )
    return "\n".join(lines)

def render_dashboard_left(app: Any) -> str:
    totals = (
        app._context_efficiency.get("totals", {})
        if app._context_efficiency
        else {}
    )
    return "\n".join(
        [
            "Dashboard",
            f"Workspaces: {app._summary.get('workspace_count', len(app._workspaces))}",
            f"Open tasks: {app._summary.get('open_task_count', 0)}",
            f"Active runs: {app._summary.get('active_run_count', 0)}",
            f"Saved tokens: {totals.get('saved_tokens', 0)} ({totals.get('savings_pct', 0)}%)",
            "",
            "Recent tasks:",
            *[
                f"- {task.get('title')} [{task.get('status')}]"
                for task in app._tasks[:6]
            ],
        ]
    )

def render_dashboard_center(app: Any) -> str:
    events = app._summary.get("recent_events", []) or []
    batons = app._summary.get("recent_batons", []) or []
    lines = ["Recent events:"]
    lines.extend(
        [
            f"- {event.get('event_type')} task={event.get('task_id')}"
            for event in events[:8]
        ]
    )
    lines.append("")
    lines.append("Recent batons:")
    lines.extend(
        [
            f"- {baton.get('summary', baton.get('id'))} task={baton.get('task_id')}"
            for baton in batons[:8]
        ]
    )
    return "\n".join(lines)

def render_metrics_left(app: Any) -> str:
    totals = (
        app._context_efficiency.get("totals", {})
        if app._context_efficiency
        else {}
    )
    cost_totals = (
        app._context_efficiency.get("cost_totals", {})
        if app._context_efficiency
        else {}
    )
    layering_modes = (
        app._context_efficiency.get("layering_modes", {})
        if app._context_efficiency
        else {}
    )
    return "\n".join(
        [
            "Context Efficiency",
            f"Bundles: {app._context_efficiency.get('bundle_count', 0)}",
            f"Raw tokens: {totals.get('raw_tokens', 0)}",
            f"Optimized tokens: {totals.get('optimized_tokens', 0)}",
            f"Saved tokens: {totals.get('saved_tokens', 0)}",
            f"Savings: {totals.get('savings_pct', 0)}%",
            f"Cost saved: {cost_totals.get('saved_usd', 'n/a')}",
            f"Layer modes: {layering_modes}",
        ]
    )

def render_metrics_center(app: Any) -> str:
    if not app._context_efficiency:
        return "No metrics available."
    by_model = app._context_efficiency.get("by_model", {}) or {}
    recent = app._context_efficiency.get("recent_bundles", []) or []
    layering_comparison = app._context_efficiency.get("layering_comparison")
    lines = ["By model:"]
    if not by_model:
        lines.append("- none")
    else:
        for model, bucket in list(by_model.items())[:12]:
            lines.append(
                f"- {model}: bundles={bucket.get('bundle_count', 0)} "
                f"saved={bucket.get('saved_tokens', 0)}"
            )
    lines.append("")
    if isinstance(layering_comparison, dict):
        lines.append("Layered vs Legacy:")
        lines.append(
            f"- bundles={layering_comparison.get('bundle_count', 0)} "
            f"saved={layering_comparison.get('saved_tokens', 0)} "
            f"({layering_comparison.get('savings_pct', 0)}%)"
        )
        lines.append("")
    lines.append("Recent bundles:")
    if not recent:
        lines.append("- none")
    else:
        for item in recent[:12]:
            lines.append(
                f"- {item.get('bundle_id')} model={item.get('target_model')} "
                f"saved={item.get('token_savings_estimate', 0)} "
                f"({item.get('token_savings_pct', 0)}%)"
            )
    return "\n".join(lines)

def render_workspaces_left(app: Any) -> str:
    lines = ["Workspaces (j/k to select)"]
    for index, workspace in enumerate(app._workspaces):
        marker = "*" if index == app._selected_workspace_index else "-"
        lines.append(f"{marker} {workspace.get('name')} ({workspace.get('id')})")
    return "\n".join(lines)

def render_workspaces_center(app: Any) -> str:
    workspace = app._selected_workspace()
    if workspace is None:
        return "No workspace registered."
    lines = [
        "Selected workspace",
        f"id: {workspace.get('id')}",
        f"name: {workspace.get('name')}",
        f"path: {workspace.get('root_path')}",
        f"branch: {workspace.get('branch') or '-'}",
        f"runtime: {workspace.get('runtime_mode')}",
        "",
        "Press s to scan selected workspace.",
    ]
    if app._last_scan:
        scan = app._last_scan.get("scan", {})
        lines.extend(
            [
                "",
                f"languages: {', '.join(scan.get('languages', [])) or '-'}",
                f"frameworks: {', '.join(scan.get('frameworks', [])) or '-'}",
                f"package managers: {', '.join(scan.get('package_managers', [])) or '-'}",
                f"docs: {', '.join(scan.get('docs', [])) or '-'}",
            ]
        )
    return "\n".join(lines)

def render_tasks_left(app: Any) -> str:
    lines = ["Tasks (j/k to select, v for detail)"]
    for index, task in enumerate(app._tasks):
        marker = "*" if index == app._selected_task_index else "-"
        lines.append(
            f"{marker} {task.get('title')} [{task.get('status')}] "
            f"{task.get('complexity')}"
        )
    return "\n".join(lines)

def render_tasks_center(app: Any) -> str:
    task = app._selected_task()
    if task is None:
        return "No tasks."
    return "\n".join(
        [
            "Selected task",
            f"id: {task.get('id')}",
            f"title: {task.get('title')}",
            f"status: {task.get('status')}",
            f"type: {task.get('task_type')}",
            f"complexity: {task.get('complexity')}",
            f"updated: {task.get('updated_at')}",
            "",
            "n=create task p=start run e=execute",
        ]
    )

def render_task_detail_left(app: Any) -> str:
    task = app._selected_task()
    if task is None:
        return "No selected task."
    lines = [
        "Task Detail",
        f"id: {task.get('id')}",
        f"title: {task.get('title')}",
        f"type: {task.get('task_type')}",
        f"complexity: {task.get('complexity')}",
        "",
        "Recent events:",
    ]
    for event in app._task_events[-8:]:
        lines.append(f"- {event.get('event_type')}")
    return "\n".join(lines)

def render_task_detail_center(app: Any) -> str:
    lines = ["Execution / Baton / Routing / Digest"]
    if app._latest_task_run:
        lines.extend(
            [
                f"latest run: {app._latest_task_run.get('status')}",
                f"run role: {app._latest_task_run.get('role')}",
            ]
        )
        output_summary = str(
            app._latest_task_run.get("output_summary") or ""
        ).strip()
        error_message = str(
            app._latest_task_run.get("error_message") or ""
        ).strip()
        if output_summary:
            lines.append(f"result: {output_summary}")
        elif error_message:
            lines.append(f"error: {error_message}")
        else:
            lines.append("result: (no output yet)")
    else:
        lines.append("latest run: none")
    if app._task_execution_report:
        changed_files = app._task_execution_report.get("changed_files") or []
        verification_commands = (
            app._task_execution_report.get("verification_commands") or []
        )
        diff_artifacts = app._task_execution_report.get("diff_artifacts") or []
        lines.extend(
            [
                "",
                f"execution outcome: {app._task_execution_report.get('outcome', '-')}",
                f"verification: {app._task_execution_report.get('verification_status', '-')}",
                f"meaningful change: {app._task_execution_report.get('meaningful_change', '-')}",
                f"changed files: {len(changed_files)}",
                f"verification commands: {len(verification_commands)}",
                f"diff artifacts: {len(diff_artifacts)}",
            ]
        )
        if changed_files:
            lines.append("changed:")
            lines.extend([f"- {path}" for path in changed_files[:5]])
        if verification_commands:
            first_command = verification_commands[0]
            lines.extend(
                [
                    "",
                    f"verify cmd: {first_command.get('command', '-')}",
                    f"verify status: {first_command.get('status', '-')}",
                ]
            )
            preview = str(first_command.get("output_preview") or "").strip()
            if preview:
                lines.append(f"verify preview: {preview[:160]}")
        if diff_artifacts:
            first_diff = diff_artifacts[0]
            lines.extend(
                [
                    "",
                    f"diff file: {first_diff.get('path', '-')}",
                    f"diff ref: {first_diff.get('ref_id', '-')}",
                ]
            )
            diff_preview = str(first_diff.get("preview") or "").strip()
            if diff_preview:
                lines.append(diff_preview[:240])
    if app._latest_run_result:
        lines.extend(
            [
                "",
                f"output ref: {app._latest_run_result.get('output_ref_id', '-')}",
                f"context ref: {app._latest_run_result.get('context_ref_id', '-')}",
                f"summary: {str(app._latest_run_result.get('output_summary') or '-')[:96]}",
            ]
        )
        output_preview = str(
            app._latest_run_result.get("output_text") or ""
        ).strip()
        if output_preview:
            lines.append(f"output preview: {output_preview[:240]}")
    if app._task_latest_baton:
        lines.append(
            f"latest baton: {app._task_latest_baton.get('summary', app._task_latest_baton.get('id'))}"
        )
    else:
        lines.append("latest baton: none")
    if app._task_routing:
        lines.append(
            f"routing: {app._task_routing.get('worker_role')} / "
            f"{app._task_routing.get('model_tier')}"
        )
    else:
        lines.append("routing: none")
    if app._task_digest:
        lines.append(
            f"digest: {app._task_digest.get('headline') or app._task_digest.get('summary', '')[:90]}"
        )
        lines.append(f"eli5: {app._task_digest.get('eli5_summary', '')[:120]}")
    else:
        lines.append("digest: none")
    lines.append("")
    lines.append("Hotkeys: g=digest o=route p=run e=execute b=back")
    return "\n".join(lines)

def render_runs_left(app: Any) -> str:
    lines = ["Agent Runs (j/k to select, v for task detail)"]
    for index, run in enumerate(app._runs):
        marker = "*" if index == app._selected_run_index else "-"
        lines.append(
            f"{marker} {run.get('id')} role={run.get('role')} "
            f"status={run.get('status')} task={run.get('task_id')}"
        )
    return "\n".join(lines)

def render_runs_center(app: Any) -> str:
    run = app._selected_run()
    if run is None:
        return "No runs."
    run_result = app._safe_request(
        lambda: app._client.get_agent_run_result(str(run.get("id"))),
        None,
    )
    lines = [
        "Selected run",
        f"id: {run.get('id')}",
        f"task_id: {run.get('task_id')}",
        f"role: {run.get('role')}",
        f"status: {run.get('status')}",
        f"updated: {run.get('updated_at')}",
    ]
    if isinstance(run_result, dict):
        lines.extend(
            [
                "",
                f"prompt ref: {run_result.get('prompt_ref_id') or '-'}",
                f"context ref: {run_result.get('context_ref_id') or '-'}",
                f"output ref: {run_result.get('output_ref_id') or '-'}",
                f"summary: {str(run_result.get('output_summary') or '-')[:120]}",
            ]
        )
    return "\n".join(lines)

def render_diagnostics_left(app: Any) -> str:
    dependencies = app._services.get("dependencies", []) if app._services else []
    lines = [
        "Diagnostics",
        f"health: {app._summary.get('health', 'unknown')}",
        "",
        "service dependencies:",
    ]
    for dependency in dependencies:
        lines.append(
            f"- {dependency.get('name')}: {dependency.get('status')} "
            f"({dependency.get('detail', '')})"
        )
    return "\n".join(lines)

def render_diagnostics_center(app: Any) -> str:
    routes = app._diag_routes.get("routes", []) if app._diag_routes else []
    return "\n".join(
        [
            "Config",
            f"runtime_mode: {app._diag_config.get('runtime_mode', '-')}",
            f"db_backend: {app._diag_config.get('db_backend', '-')}",
            f"redis_required: {app._diag_config.get('redis_required', '-')}",
            "",
            f"routes_count: {len(routes)}",
            f"sample_routes: {', '.join(routes[:6]) if routes else '-'}",
        ]
    )

def render_notifications_left(app: Any) -> str:
    lines = ["Notifications (j/k select, h ack)"]
    if not app._notifications:
        lines.append("- none")
        return "\n".join(lines)
    for index, item in enumerate(app._notifications):
        marker = "*" if index == app._selected_notification_index else "-"
        lines.append(f"{marker} [{item.get('category')}] {item.get('title')}")
    return "\n".join(lines)

def render_notifications_center(app: Any) -> str:
    item = app._selected_notification()
    if item is None:
        return "No unread notifications."
    return "\n".join(
        [
            "Selected notification",
            f"id: {item.get('id')}",
            f"category: {item.get('category')}",
            f"title: {item.get('title')}",
            f"body: {item.get('body')}",
            f"task: {item.get('related_task_id') or '-'}",
            f"workspace: {item.get('related_workspace_id') or '-'}",
            f"finding: {item.get('finding_id') or '-'}",
            f"created_at: {item.get('created_at')}",
        ]
    )
