from __future__ import annotations

from types import SimpleNamespace

from packages.contracts.python.models import ProjectEventCreate

from app.services.autonomy_stage_models import AutonomyStageContext


class AutonomyStageExecutor:
    def __init__(
        self,
        *,
        store,
        run_execution_service,
        workspace_execution_enabled: bool,
        workspace_execution_profile: str,
        workspace_max_steps: int,
        parse_positive_int,
    ) -> None:
        self._store = store
        self._run_execution_service = run_execution_service
        self._workspace_execution_enabled = workspace_execution_enabled
        self._workspace_execution_profile = workspace_execution_profile
        self._workspace_max_steps = workspace_max_steps
        self._parse_positive_int = parse_positive_int

    def execute(self, *, context: AutonomyStageContext, request, provider, model):
        if (
            context.stage == "execute"
            and context.task.workspace_id is not None
            and self._workspace_execution_enabled
            and (
                context.prefs.get("workspace_execution_enabled") is None
                or _as_bool(context.prefs.get("workspace_execution_enabled"))
            )
        ):
            self._store.save_project_event(
                ProjectEventCreate(
                    task_id=context.task.id,
                    event_type="autonomy.execution.mode",
                    event_data={
                        "mode": "workspace",
                        "profile": str(
                            context.prefs.get("workspace_policy_profile")
                            or self._workspace_execution_profile
                        ),
                        "autonomy_mode": context.autonomy_mode,
                    },
                )
            )
            workspace_result = self._run_execution_service.execute_workspace_loop(
                request,
                max_steps=self._parse_positive_int(
                    context.prefs.get("workspace_max_steps"),
                    default=self._workspace_max_steps,
                    maximum=8,
                ),
                policy_profile=str(
                    context.prefs.get("workspace_policy_profile")
                    or self._workspace_execution_profile
                ),
                require_approval=context.requires_approval,
                dry_run=context.autonomy_mode == "observe",
            )
            return SimpleNamespace(
                run_id=None,
                provider=str(workspace_result.get("provider") or (provider or "")),
                target_model=str(workspace_result.get("target_model") or model),
                output_text=str(workspace_result.get("digest") or workspace_result),
            )
        return self._run_execution_service.execute(request)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return value != 0
    return False
