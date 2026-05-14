from __future__ import annotations

from typing import Callable

import typer

from syncore_cli.client import SyncoreApiClient, SyncoreApiError


ClientFactory = Callable[[], SyncoreApiClient]
ResolveWorkspaceId = Callable[[SyncoreApiClient, str], str]
TaskDetailLines = Callable[
    [dict[str, object], list[dict[str, object]], dict[str, object] | None, dict[str, object] | None, dict[str, object] | None],
    list[str],
]
LatestModelSwitch = Callable[[list[dict[str, object]]], dict[str, object] | None]


def register_task_commands(
    task_app: typer.Typer,
    root_app: typer.Typer,
    *,
    client_factory: ClientFactory,
    resolve_workspace_id: ResolveWorkspaceId,
    task_detail_lines: TaskDetailLines,
    latest_model_switch: LatestModelSwitch,
    print_error: Callable[[str], None],
    print_json: Callable[[object], None],
    print_kv_panel: Callable[[str, object], None],
    print_lines_panel: Callable[[str, list[str]], None],
    print_table: Callable[[str, list[str], list[list[str]]], None],
) -> None:
    @task_app.command("list")
    def task_list(
        workspace: str | None = typer.Option(None, "--workspace"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        client = client_factory()
        try:
            workspace_id = resolve_workspace_id(client, workspace) if workspace else None
            tasks = client.list_tasks(workspace_id=workspace_id)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        if json_output:
            print_json(tasks)
            return

        rows = [
            [
                str(task.get("id")),
                str(task.get("title")),
                str(task.get("status")),
                str(task.get("complexity")),
                str(task.get("workspace_id") or ""),
                str(task.get("updated_at")),
            ]
            for task in tasks
        ]
        print_table(
            "Tasks",
            ["id", "title", "status", "complexity", "workspace_id", "updated_at"],
            rows,
        )

    @task_app.command("create")
    def task_create(
        title: str,
        workspace: str | None = typer.Option(None, "--workspace"),
        description: str | None = typer.Option(None, "--description"),
        task_type: str = typer.Option("implementation", "--type"),
        complexity: str = typer.Option("medium", "--complexity"),
    ) -> None:
        client = client_factory()
        workspace_id: str | None = None
        if workspace:
            try:
                workspace_id = resolve_workspace_id(client, workspace)
            except SyncoreApiError as error:
                print_error(str(error))
                raise typer.Exit(code=1)

        full_title = f"{title} - {description}" if description else title
        payload = {
            "title": full_title,
            "task_type": task_type,
            "complexity": complexity,
            "workspace_id": workspace_id,
        }
        try:
            task = client.create_task(payload)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        print_json(task)

    @task_app.command("show")
    def task_show(task_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
        client = client_factory()
        try:
            task = client.get_task(task_id)
            events = client.list_task_events(task_id)
            try:
                baton = client.latest_task_baton(task_id)
            except SyncoreApiError:
                baton = None
            try:
                digest = client.get_task_digest(task_id)
            except SyncoreApiError:
                digest = None
            try:
                model_switches = client.list_task_model_switches(task_id, limit=25)
            except SyncoreApiError:
                model_switches = []
            try:
                model_policy = client.get_task_model_policy(task_id)
            except SyncoreApiError:
                model_policy = None
            try:
                execution_report = client.get_task_execution_report(task_id)
            except SyncoreApiError:
                execution_report = None
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        payload = {
            "task": task,
            "recent_events": events,
            "latest_baton": baton,
            "digest": digest,
            "execution_report": execution_report,
            "latest_model_switch": latest_model_switch(events),
            "model_switches": model_switches,
            "model_policy": model_policy,
        }
        if json_output:
            print_json(payload)
            return
        print_lines_panel(
            "Task Detail",
            task_detail_lines(task, events, baton, digest, execution_report),
        )

    @task_app.command("model-policy")
    def task_model_policy(
        task_id: str,
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        client = client_factory()
        try:
            policy = client.get_task_model_policy(task_id)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        if json_output:
            print_json(policy)
            return
        print_kv_panel("Task Model Policy", policy)

    @task_app.command("set-model-policy")
    def task_set_model_policy(
        task_id: str,
        default_provider: str | None = typer.Option(None, "--default-provider"),
        default_model: str | None = typer.Option(None, "--default-model"),
        plan_provider: str | None = typer.Option(None, "--plan-provider"),
        plan_model: str | None = typer.Option(None, "--plan-model"),
        execute_provider: str | None = typer.Option(None, "--execute-provider"),
        execute_model: str | None = typer.Option(None, "--execute-model"),
        review_provider: str | None = typer.Option(None, "--review-provider"),
        review_model: str | None = typer.Option(None, "--review-model"),
        fallback_order: str | None = typer.Option(None, "--fallback-order"),
        prefer_reviewer_provider: bool | None = typer.Option(None, "--prefer-reviewer-provider/--no-prefer-reviewer-provider"),
        optimization_goal: str | None = typer.Option(None, "--optimization-goal"),
        allow_cross_provider_switching: bool | None = typer.Option(None, "--allow-cross-provider-switching/--no-allow-cross-provider-switching"),
        maintain_context_continuity: bool | None = typer.Option(None, "--maintain-context-continuity/--no-maintain-context-continuity"),
        minimum_context_window: int | None = typer.Option(None, "--minimum-context-window"),
        max_latency_tier: str | None = typer.Option(None, "--max-latency-tier"),
        max_cost_tier: str | None = typer.Option(None, "--max-cost-tier"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        client = client_factory()
        payload: dict[str, object] = {}
        mapping = {
            "default_provider": default_provider,
            "default_model": default_model,
            "plan_provider": plan_provider,
            "plan_model": plan_model,
            "execute_provider": execute_provider,
            "execute_model": execute_model,
            "review_provider": review_provider,
            "review_model": review_model,
        }
        for key, value in mapping.items():
            if value is not None:
                payload[key] = value
        if fallback_order is not None:
            payload["fallback_order"] = [item.strip() for item in fallback_order.split(",") if item.strip()]
        if prefer_reviewer_provider is not None:
            payload["prefer_reviewer_provider"] = prefer_reviewer_provider
        if optimization_goal is not None:
            payload["optimization_goal"] = optimization_goal
        if allow_cross_provider_switching is not None:
            payload["allow_cross_provider_switching"] = allow_cross_provider_switching
        if maintain_context_continuity is not None:
            payload["maintain_context_continuity"] = maintain_context_continuity
        if minimum_context_window is not None:
            payload["minimum_context_window"] = minimum_context_window
        if max_latency_tier is not None:
            payload["max_latency_tier"] = max_latency_tier
        if max_cost_tier is not None:
            payload["max_cost_tier"] = max_cost_tier
        try:
            policy = client.update_task_model_policy(task_id, payload)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        if json_output:
            print_json(policy)
            return
        print_kv_panel("Updated Task Model Policy", policy)

    @task_app.command("switch-model")
    def task_switch_model(
        task_id: str,
        provider: str = typer.Option(..., "--provider"),
        model: str = typer.Option(..., "--model"),
        target_agent: str = typer.Option("coder", "--target-agent"),
        token_budget: int = typer.Option(8000, "--token-budget"),
        reason: str | None = typer.Option(None, "--reason"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        client = client_factory()
        payload = {
            "provider": provider,
            "model": model,
            "target_agent": target_agent,
            "token_budget": token_budget,
            "reason": reason,
        }
        try:
            result = client.switch_task_model(task_id, payload)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        if json_output:
            print_json(result)
            return
        print_kv_panel("Task Model Switch", result)

    @task_app.command("set-prefs")
    def task_set_prefs(
        task_id: str,
        preferred_agent_role: str = typer.Option("coder", "--agent-role"),
        preferred_provider: str = typer.Option("", "--provider"),
        preferred_model: str = typer.Option("", "--model"),
        execution_prompt: str = typer.Option("", "--prompt"),
        requires_approval: bool = typer.Option(False, "--requires-approval"),
        sdlc_enforce: bool = typer.Option(False, "--sdlc-enforce"),
    ) -> None:
        client = client_factory()
        payload = {
            "task_id": task_id,
            "event_type": "task.preferences",
            "event_data": {
                "preferred_agent_role": preferred_agent_role.strip().lower() or "coder",
                "execution_prompt": execution_prompt.strip(),
                "requires_approval": "true" if requires_approval else "false",
                "sdlc_enforce": "true" if sdlc_enforce else "false",
            },
        }
        provider = preferred_provider.strip().lower()
        model = preferred_model.strip()
        if provider:
            payload["event_data"]["preferred_provider"] = provider
        if model:
            payload["event_data"]["preferred_model"] = model
        try:
            event = client.create_project_event(payload)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        print_json(event)

    @root_app.command("events")
    def events(task_id: str) -> None:
        client = client_factory()
        try:
            payload = client.list_task_events(task_id)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        print_json(payload)

    @root_app.command(
        "inspect",
        help="Inspect a task with execution outcome, digest, baton, and recent event context in one operator-friendly view.",
    )
    def inspect_task(task_id: str) -> None:
        task_show(task_id, json_output=False)

    @root_app.command("baton")
    def baton(task_id: str) -> None:
        client = client_factory()
        try:
            latest = client.latest_task_baton(task_id)
        except SyncoreApiError:
            latest = None

        try:
            packets = client.list_task_batons(task_id)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        print_json({"latest": latest, "packets": packets})

    @root_app.command("route")
    def route(task_id: str) -> None:
        client = client_factory()
        try:
            task_detail = client.get_task(task_id)
            task = task_detail.get("task", {})
            decision = client.route_next_action(
                {
                    "task_type": task.get("task_type", "analysis"),
                    "complexity": task.get("complexity", "medium"),
                    "requires_memory": True,
                }
            )
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        print_json(decision)

    @root_app.command("digest")
    def digest(task_id: str) -> None:
        client = client_factory()
        try:
            payload = client.generate_digest({"task_id": task_id, "limit": 50})
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        print_json(payload)
