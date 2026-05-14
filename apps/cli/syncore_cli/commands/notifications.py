from __future__ import annotations

from typing import Callable

import typer

from syncore_cli.client import SyncoreApiClient, SyncoreApiError


ClientFactory = Callable[[], SyncoreApiClient]


def register_notification_commands(
    notifications_app: typer.Typer,
    *,
    client_factory: ClientFactory,
    print_error: Callable[[str], None],
    print_json: Callable[[object], None],
    print_kv_panel: Callable[[str, object], None],
    print_table: Callable[[str, list[str], list[list[str]]], None],
) -> None:
    @notifications_app.command("list")
    def notifications_list(
        json_output: bool = typer.Option(False, "--json"),
        acknowledged: bool | None = typer.Option(None, "--acknowledged"),
        limit: int = typer.Option(100, "--limit", min=1, max=500),
    ) -> None:
        client = client_factory()
        try:
            payload = client.list_notifications(acknowledged=acknowledged, limit=limit)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        items = payload.get("items", []) if isinstance(payload, dict) else []
        if json_output:
            print_json(payload)
            return
        rows = [
            [
                str(item.get("id")),
                str(item.get("category")),
                str(item.get("title")),
                "yes" if item.get("acknowledged") else "no",
                str(item.get("created_at")),
            ]
            for item in items
        ]
        print_table(
            "Notifications",
            ["id", "category", "title", "ack", "created_at"],
            rows,
        )

    @notifications_app.command("show")
    def notifications_show(
        notification_id: str, json_output: bool = typer.Option(False, "--json")
    ) -> None:
        client = client_factory()
        try:
            payload = client.get_notification(notification_id)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        if json_output:
            print_json(payload)
            return
        print_kv_panel("Notification", payload)

    @notifications_app.command("ack")
    def notifications_ack(
        notification_id: str, json_output: bool = typer.Option(False, "--json")
    ) -> None:
        client = client_factory()
        try:
            payload = client.acknowledge_notification(notification_id)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)
        if json_output:
            print_json(payload)
            return
        print_kv_panel("Acknowledged", payload)
