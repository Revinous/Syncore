from __future__ import annotations

from dataclasses import dataclass

from packages.contracts.python.models import Task


@dataclass
class AutonomyStageContext:
    task: Task
    prefs: dict[str, str]
    stage: str
    cycle: int
    execute_role: str
    autonomy_mode: str
    requires_approval: bool
    enforce_sdlc: bool
    max_cycles: int
    max_retries: int
