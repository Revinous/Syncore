from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def print_json(payload: Any) -> None:
    console.print_json(data=payload)


def print_error(message: str) -> None:
    console.print(f"[red]Error:[/red] {message}")


def print_status_table(health: dict[str, Any], services: dict[str, Any]) -> None:
    table = Table(title="Syncore Status")
    table.add_column("Component")
    table.add_column("Status")
    table.add_row("orchestrator", str(health.get("status", "unknown")))
    for dependency in services.get("dependencies", []):
        table.add_row(str(dependency.get("name")), str(dependency.get("status")))
    console.print(table)


def print_kv_panel(title: str, payload: dict[str, Any]) -> None:
    console.print(Panel(json.dumps(payload, indent=2, sort_keys=True), title=title))


def print_table(title: str, columns: list[str], rows: list[list[str]]) -> None:
    table = Table(title=title)
    for column in columns:
        table.add_column(column)
    for row in rows:
        table.add_row(*row)
    console.print(table)
