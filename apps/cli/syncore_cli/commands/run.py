from __future__ import annotations

from typing import Callable

import typer

from syncore_cli.client import SyncoreApiClient, SyncoreApiError


ClientFactory = Callable[[], SyncoreApiClient]
RunResultLines = Callable[[dict[str, object]], list[str]]
TruncateText = Callable[[object, int], str]


def register_run_commands(
    run_app: typer.Typer,
    *,
    client_factory: ClientFactory,
    run_result_lines: RunResultLines,
    truncate_text: TruncateText,
    print_error: Callable[[str], None],
    print_json: Callable[[object], None],
    print_kv_panel: Callable[[str, object], None],
    print_lines_panel: Callable[[str, list[str]], None],
    print_table: Callable[[str, list[str], list[list[str]]], None],
) -> None:
    @run_app.command("list")
    def run_list() -> None:
        client = client_factory()
        try:
            runs = client.list_agent_runs()
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        rows = [
            [
                str(run.get("id")),
                str(run.get("task_id")),
                str(run.get("role")),
                str(run.get("status")),
                truncate_text(run.get("output_summary") or run.get("error_message") or "", 48),
                str(run.get("updated_at")),
            ]
            for run in runs
        ]
        print_table(
            "Agent Runs",
            ["id", "task_id", "role", "status", "result", "updated_at"],
            rows,
        )

    @run_app.command("start")
    def run_start(
        task_id: str, agent_role: str = typer.Option(..., "--agent-role")
    ) -> None:
        client = client_factory()
        try:
            run = client.create_agent_run(
                {
                    "task_id": task_id,
                    "role": agent_role,
                    "status": "queued",
                }
            )
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        print_json(run)

    @run_app.command("execute")
    def run_execute(
        task_id: str,
        prompt: str = typer.Argument(...),
        target_agent: str = typer.Option("coder", "--target-agent"),
        token_budget: int = typer.Option(8000, "--token-budget"),
        provider: str | None = typer.Option(None, "--provider"),
        model: str | None = typer.Option(None, "--model"),
        agent_role: str = typer.Option("coder", "--agent-role"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        client = client_factory()
        payload = {
            "task_id": task_id,
            "prompt": prompt,
            "target_agent": target_agent,
            "token_budget": token_budget,
            "provider": provider,
            "target_model": model,
            "agent_role": agent_role,
        }
        try:
            response = client.execute_run_auto(payload)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        if json_output:
            print_json(response)
            return
        print_kv_panel("Run Executed", response)

    @run_app.command("result")
    def run_result(
        run_id: str,
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        client = client_factory()
        try:
            result = client.get_agent_run_result(run_id)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        if json_output:
            print_json(result)
            return
        print_lines_panel("Run Result", run_result_lines(result))

    @run_app.command("cancel")
    def run_cancel(run_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
        client = client_factory()
        try:
            payload = client.cancel_agent_run(run_id)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        if json_output:
            print_json(payload)
            return
        print_kv_panel("Run Canceled", payload)

    @run_app.command("resume")
    def run_resume(run_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
        client = client_factory()
        try:
            payload = client.resume_agent_run(run_id)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        if json_output:
            print_json(payload)
            return
        print_kv_panel("Run Resumed", payload)
