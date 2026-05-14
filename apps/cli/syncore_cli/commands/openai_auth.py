from __future__ import annotations

from typing import Callable

import typer

from syncore_cli.openai_auth import OpenAIAuthError, OpenAIAuthStore, OpenAIModelClient, OpenAICredentials


OpenAIStoreFactory = Callable[[], OpenAIAuthStore]
OpenAIModelClientFactory = Callable[[], OpenAIModelClient]


def register_openai_auth_commands(
    openai_auth_app: typer.Typer,
    *,
    store_factory: OpenAIStoreFactory,
    models_client_factory: OpenAIModelClientFactory,
    print_error: Callable[[str], None],
    print_json: Callable[[object], None],
    print_table: Callable[[str, list[str], list[list[str]]], None],
) -> None:
    @openai_auth_app.command("login")
    def openai_login(
        api_key: str = typer.Option("", "--api-key", prompt=True, hide_input=True)
    ) -> None:
        if not api_key.strip():
            print_error("API key cannot be empty")
            raise typer.Exit(code=1)

        store = store_factory()
        models_client = models_client_factory()
        try:
            models = models_client.list_text_models(api_key.strip())
        except OpenAIAuthError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        store.save(OpenAICredentials(api_key=api_key.strip()))
        print_json(
            {
                "status": "connected",
                "credential_path": str(store.path),
                "available_models": models[:25],
                "model_count": len(models),
            }
        )

    @openai_auth_app.command("logout")
    def openai_logout() -> None:
        store = store_factory()
        store.clear()
        print_json({"status": "disconnected"})

    @openai_auth_app.command("status")
    def openai_status() -> None:
        store = store_factory()
        credentials = store.load()
        if credentials is None:
            print_json({"connected": False, "credential_path": str(store.path)})
            return
        print_json({"connected": True, "credential_path": str(store.path)})

    @openai_auth_app.command("models")
    def openai_models(json_output: bool = typer.Option(False, "--json")) -> None:
        store = store_factory()
        credentials = store.load()
        if credentials is None:
            print_error("Not connected. Run `syncore auth openai login`.")
            raise typer.Exit(code=1)

        models_client = models_client_factory()
        try:
            models = models_client.list_text_models(credentials.api_key)
        except OpenAIAuthError as error:
            print_error(str(error))
            raise typer.Exit(code=1)

        if json_output:
            print_json({"models": models, "count": len(models)})
            return

        rows = [[model] for model in models]
        print_table("OpenAI Models", ["id"], rows)
