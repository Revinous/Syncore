from __future__ import annotations

from typing import Callable

import typer

from syncore_cli.client import SyncoreApiClient, SyncoreApiError


ClientFactory = Callable[[], SyncoreApiClient]


def register_metrics_commands(
    metrics_app: typer.Typer,
    *,
    client_factory: ClientFactory,
    print_error: Callable[[str], None],
    print_json: Callable[[object], None],
    print_kv_panel: Callable[[str, object], None],
    print_table: Callable[[str, list[str], list[list[str]]], None],
) -> None:
    @metrics_app.command("context")
    def metrics_context(
        json_output: bool = typer.Option(False, "--json"),
        limit: int = typer.Option(200, "--limit", min=1, max=1000),
    ) -> None:
        client = client_factory()
        try:
            payload = client.context_efficiency_metrics(limit=limit)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        if json_output:
            print_json(payload)
            return

        totals = payload.get("totals", {})
        print_kv_panel(
            "Context Efficiency",
            {
                "bundle_count": payload.get("bundle_count", 0),
                "raw_tokens": totals.get("raw_tokens", 0),
                "optimized_tokens": totals.get("optimized_tokens", 0),
                "saved_tokens": totals.get("saved_tokens", 0),
                "savings_pct": totals.get("savings_pct", 0),
                "cost_saved_usd": (payload.get("cost_totals") or {}).get("saved_usd", "n/a"),
            },
        )

    @metrics_app.command("layering")
    def metrics_layering(
        json_output: bool = typer.Option(False, "--json"),
        limit: int = typer.Option(500, "--limit", min=1, max=2000),
    ) -> None:
        client = client_factory()
        try:
            payload = client.context_efficiency_metrics(limit=limit)
        except SyncoreApiError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        if json_output:
            print_json(payload.get("layering_profiles", {}))
            return

        profiles = payload.get("layering_profiles", {})
        if not isinstance(profiles, dict) or not profiles:
            print_kv_panel("Layering Rollout", {"profiles": 0})
            return

        rows: list[list[str]] = []
        for profile, stats in profiles.items():
            if not isinstance(stats, dict):
                continue
            legacy_tokens = int(stats.get("legacy_tokens", 0) or 0)
            layered_tokens = int(stats.get("layered_tokens", 0) or 0)
            comparison_count = int(stats.get("comparison_count", 0) or 0)
            delta = legacy_tokens - layered_tokens
            pct = round((delta / legacy_tokens) * 100.0, 2) if legacy_tokens > 0 else 0.0
            rows.append(
                [
                    str(profile),
                    str(stats.get("bundle_count", 0)),
                    str(stats.get("layering_modes", {})),
                    str(delta),
                    f"{pct}%",
                    str(comparison_count),
                ]
            )
        rows.sort(key=lambda row: row[0])
        print_table(
            "Layering Rollout Profiles",
            ["profile", "bundles", "modes", "token_delta", "delta_pct", "samples"],
            rows,
        )
