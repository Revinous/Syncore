from __future__ import annotations

import re

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

TASK_TYPES = (
    "analysis",
    "implementation",
    "integration",
    "review",
    "memory_retrieval",
    "memory_update",
)
COMPLEXITY_LEVELS = ("low", "medium", "high")
AGENT_ROLES = ("planner", "coder", "reviewer", "analyst", "memory")
MODEL_PROVIDERS = ("local_echo", "openai", "anthropic", "google", "xai", "other")
PROVIDER_MODEL_CATALOG: dict[str, list[str]] = {
    "local_echo": ["local_echo"],
    "openai": ["gpt-5.4", "gpt-5.5", "gpt-5.2-codex"],
    "anthropic": ["claude-sonnet-4-20250514", "claude-3-7-sonnet-latest"],
    "google": ["gemini-2.5-pro", "gemini-2.5-flash"],
    "xai": ["grok-3", "grok-3-mini"],
    "other": [],
}
DEFAULT_PROVIDER = "local_echo"
DEFAULT_MODEL = "local_echo"


class NewTaskScreen(ModalScreen[dict[str, str] | None]):
    CSS = """
    #new-task-modal {
      width: 84;
      height: auto;
      border: round $accent;
      padding: 1 2;
      background: $surface;
      align-horizontal: center;
      align-vertical: middle;
    }
    #new-task-actions {
      height: auto;
      layout: horizontal;
      margin-top: 1;
    }
    #new-task-actions Button {
      margin-right: 1;
    }
    #new-task-error {
      color: $error;
      height: auto;
      margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+n", "next_model", "Next Model"),
        ("ctrl+p", "prev_model", "Prev Model"),
        ("tab", "complete_model", "Complete Model"),
    ]

    def __init__(
        self,
        workspace_name: str | None = None,
        available_models: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._workspace_name = workspace_name
        self._available_models = available_models or []
        self._matching_models: list[str] = list(self._available_models[:10])
        self._model_cursor = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="new-task-modal"):
            yield Label("Create Task")
            yield Label(f"Workspace: {self._workspace_name or 'none'}")
            yield Input(
                value=DEFAULT_PROVIDER,
                placeholder="provider (local_echo|openai|anthropic|google|xai|other)",
                id="task-provider",
            )
            yield Input(
                value="", placeholder="preferred_model (required)", id="task-model"
            )
            if self._available_models:
                yield Label(
                    "Available models: " + ", ".join(self._available_models[:12]),
                    id="task-model-list",
                )
            yield Input(value="medium", placeholder="complexity", id="task-complexity")
            yield Input(placeholder="Task title", id="task-title")
            yield Input(placeholder="Description (optional)", id="task-description")
            yield Input(value="implementation", placeholder="task_type", id="task-type")
            yield Input(
                value="coder", placeholder="preferred_agent_role", id="task-agent-role"
            )
            yield Input(
                value="false",
                placeholder="requires_approval (true/false)",
                id="task-requires-approval",
            )
            yield Input(
                value="true",
                placeholder="sdlc_enforce (true/false)",
                id="task-sdlc-enforce",
            )
            yield Input(placeholder="execution prompt (optional)", id="task-prompt")
            yield Static("", id="new-task-error")
            with Horizontal(id="new-task-actions"):
                yield Button("Create", id="new-task-create", variant="success")
                yield Button("Cancel", id="new-task-cancel")

    def on_mount(self) -> None:
        self.query_one("#task-provider", Input).focus()
        self._refresh_model_matches()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_next_model(self) -> None:
        if not self._matching_models:
            return
        self._model_cursor = (self._model_cursor + 1) % len(self._matching_models)
        self._apply_selected_model()

    def action_prev_model(self) -> None:
        if not self._matching_models:
            return
        self._model_cursor = (self._model_cursor - 1) % len(self._matching_models)
        self._apply_selected_model()

    def action_complete_model(self) -> None:
        if not self._matching_models:
            return
        self._apply_selected_model()
        self.query_one("#task-prompt", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "task-prompt":
            self._submit()
            return
        if event.input.id == "task-model":
            if self._matching_models:
                self._apply_selected_model()
            self.query_one("#task-complexity", Input).focus()
            return
        if event.input.id == "task-provider":
            self.query_one("#task-model", Input).focus()
            return
        next_field = {
            "task-complexity": "task-title",
            "task-title": "task-description",
            "task-description": "task-type",
            "task-type": "task-agent-role",
            "task-agent-role": "task-requires-approval",
            "task-requires-approval": "task-sdlc-enforce",
            "task-sdlc-enforce": "task-prompt",
        }.get(event.input.id or "")
        if next_field:
            self.query_one(f"#{next_field}", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in {"task-model", "task-provider"}:
            self._refresh_model_matches()

    def _provider_filtered_models(self) -> list[str]:
        provider = (
            self.query_one("#task-provider", Input).value.strip().lower()
            or DEFAULT_PROVIDER
        )
        if provider == "other":
            return list(self._available_models)
        catalog_models = PROVIDER_MODEL_CATALOG.get(provider, [])
        if provider == "openai":
            dynamic_openai = [
                m
                for m in self._available_models
                if m.startswith(("gpt", "o1", "o3", "o4"))
            ]
            for model in dynamic_openai:
                if model not in catalog_models:
                    catalog_models.append(model)
        return catalog_models if catalog_models else list(self._available_models)

    def _refresh_model_matches(self) -> None:
        scoped_models = self._provider_filtered_models()
        if not scoped_models:
            return
        query = self.query_one("#task-model", Input).value.strip()
        if not query:
            self._matching_models = list(scoped_models[:10])
            self._model_cursor = 0
            self._render_model_matches()
            return
        try:
            pattern = re.compile(query, re.IGNORECASE)
            matches = [model for model in scoped_models if pattern.search(model)]
        except re.error:
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            matches = [model for model in scoped_models if pattern.search(model)]
        self._matching_models = matches[:10]
        self._model_cursor = 0
        self._render_model_matches()

    def _render_model_matches(self) -> None:
        if not self._available_models:
            return
        label = self.query_one("#task-model-list", Label)
        provider = (
            self.query_one("#task-provider", Input).value.strip().lower() or "all"
        )
        if not self._matching_models:
            label.update(f"Model matches ({provider}, regex): no matches")
            return
        rendered = [
            f"{'>' if index == self._model_cursor else '-'} {model}"
            for index, model in enumerate(self._matching_models)
        ]
        label.update(f"Model matches ({provider}, regex): " + " | ".join(rendered))

    def _apply_selected_model(self) -> None:
        if not self._matching_models:
            return
        self.query_one("#task-model", Input).value = self._matching_models[
            self._model_cursor
        ]
        self._render_model_matches()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-task-cancel":
            self.dismiss(None)
            return
        if event.button.id == "new-task-create":
            self._submit()

    def _submit(self) -> None:
        provider = self.query_one("#task-provider", Input).value.strip().lower()
        title = self.query_one("#task-title", Input).value.strip()
        description = self.query_one("#task-description", Input).value.strip()
        task_type = self.query_one("#task-type", Input).value.strip().lower()
        complexity = self.query_one("#task-complexity", Input).value.strip().lower()
        agent_role = self.query_one("#task-agent-role", Input).value.strip().lower()
        requires_approval = (
            self.query_one("#task-requires-approval", Input).value.strip().lower()
        )
        sdlc_enforce = self.query_one("#task-sdlc-enforce", Input).value.strip().lower()
        preferred_model = self.query_one("#task-model", Input).value.strip()
        prompt = self.query_one("#task-prompt", Input).value.strip()
        if not title:
            self.query_one("#new-task-error", Static).update("Task title is required.")
            return
        if not provider:
            self.query_one("#new-task-error", Static).update("Provider is required.")
            return
        if provider not in MODEL_PROVIDERS:
            provider = "other"
        if task_type not in TASK_TYPES:
            task_type = "implementation"
        if complexity not in COMPLEXITY_LEVELS:
            complexity = "medium"
        if agent_role not in AGENT_ROLES:
            agent_role = "coder"
        if not preferred_model:
            self.query_one("#new-task-error", Static).update("Model is required.")
            return
        self.dismiss(
            {
                "title": title,
                "description": description,
                "preferred_provider": provider,
                "task_type": task_type,
                "complexity": complexity,
                "preferred_agent_role": agent_role,
                "preferred_model": preferred_model,
                "execution_prompt": prompt,
                "requires_approval": "true"
                if requires_approval in {"true", "1", "yes", "on"}
                else "false",
                "sdlc_enforce": "true"
                if sdlc_enforce in {"true", "1", "yes", "on"}
                else "false",
            }
        )


class OpenAISignInScreen(ModalScreen[dict[str, str] | None]):
    CSS = """
    #openai-login-modal {
      width: 76;
      height: auto;
      border: round $accent;
      padding: 1 2;
      background: $surface;
      align-horizontal: center;
      align-vertical: middle;
    }
    #openai-login-actions {
      height: auto;
      layout: horizontal;
      margin-top: 1;
    }
    #openai-login-actions Button {
      margin-right: 1;
    }
    #openai-login-error {
      color: $error;
      height: auto;
      margin-top: 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="openai-login-modal"):
            yield Label("Connect OpenAI")
            yield Label(
                "Paste API key (stored locally at ~/.syncore/openai_credentials.json)"
            )
            yield Input(password=True, placeholder="sk-...", id="openai-api-key")
            yield Static("", id="openai-login-error")
            with Horizontal(id="openai-login-actions"):
                yield Button("Connect", id="openai-login-connect", variant="success")
                yield Button("Cancel", id="openai-login-cancel")

    def on_mount(self) -> None:
        self.query_one("#openai-api-key", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "openai-api-key":
            self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "openai-login-cancel":
            self.dismiss(None)
            return
        if event.button.id == "openai-login-connect":
            self._submit()

    def _submit(self) -> None:
        api_key = self.query_one("#openai-api-key", Input).value.strip()
        if not api_key:
            self.query_one("#openai-login-error", Static).update("API key is required.")
            return
        self.dismiss({"api_key": api_key})
