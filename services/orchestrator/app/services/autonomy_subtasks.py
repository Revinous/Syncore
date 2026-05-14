from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from packages.contracts.python.models import ProjectEventCreate, Task, TaskCreate
from services.memory import MemoryStoreProtocol

AsBoolFunc = Callable[[str | None], bool]
ParsePositiveIntFunc = Callable[[str | None], int]


@dataclass(slots=True)
class SubtaskFanoutCoordinator:
    store: MemoryStoreProtocol
    default_provider: str
    default_model: str
    as_bool: AsBoolFunc
    parse_positive_int: ParsePositiveIntFunc

    def spawn_once(self, *, task: Task, prefs: dict[str, str]) -> None:
        if not self.as_bool(prefs.get("auto_spawn")):
            return
        existing_events = self.store.list_project_events(task_id=task.id, limit=500)
        for event in reversed(existing_events):
            if event.event_type == "autonomy.subtasks.spawned":
                return

        count = self.parse_positive_int(prefs.get("auto_spawn_count"))
        templates = [
            (
                "Requirements and design pass",
                "analysis",
                "false",
                (
                    "Inspect the repository and identify one safe, high-confidence improvement. "
                    "Do not modify files. Summarize the candidate change, target files, risks, and "
                    "the verification command the implementation pass should run."
                ),
            ),
            (
                "Implementation pass",
                "implementation",
                prefs.get("workspace_execution_enabled", "true"),
                prefs.get("execution_prompt", ""),
            ),
            (
                "Verification and release pass",
                "review",
                "false",
                (
                    "Review the selected improvement and its verification evidence. "
                    "Do not modify files. State whether the change is safe to ship, "
                    "what risks remain, and what final check or note should be recorded."
                ),
            ),
            (
                "Documentation and polish pass",
                "integration",
                "false",
                (
                    "Review whether any docs or operator notes should be updated for the chosen "
                    "improvement. Do not modify files unless explicitly required by the task."
                ),
            ),
        ]
        selected = templates[:count]
        spawned_ids: list[str] = []
        for title_suffix, task_type, workspace_enabled, child_execution_prompt in selected:
            child = self.store.create_task(
                TaskCreate(
                    title=f"{task.title} :: {title_suffix}",
                    task_type=task_type,  # type: ignore[arg-type]
                    complexity=task.complexity,
                    workspace_id=task.workspace_id,
                )
            )
            child_event_data: dict[str, str] = dict(prefs)
            child_event_data.update(
                {
                    "parent_task_id": str(task.id),
                    "preferred_agent_role": prefs.get("preferred_agent_role", "coder"),
                    "preferred_provider": prefs.get(
                        "preferred_provider", self.default_provider
                    ),
                    "preferred_model": prefs.get("preferred_model", self.default_model),
                    "execution_prompt": child_execution_prompt,
                    "requires_approval": prefs.get("requires_approval", "false"),
                    "sdlc_enforce": prefs.get("sdlc_enforce", "false"),
                    "workspace_execution_enabled": workspace_enabled,
                    "auto_spawn": "false",
                }
            )
            self.store.save_project_event(
                ProjectEventCreate(
                    task_id=child.id,
                    event_type="task.preferences",
                    event_data=child_event_data,
                )
            )
            spawned_ids.append(str(child.id))

        self.store.save_project_event(
            ProjectEventCreate(
                task_id=task.id,
                event_type="autonomy.subtasks.spawned",
                event_data={
                    "count": len(spawned_ids),
                    "child_task_ids": ",".join(spawned_ids),
                },
            )
        )
