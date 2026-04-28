from fastapi import FastAPI

from app.api.routes.agent_runs import router as agent_runs_router
from app.api.routes.analyst import router as analyst_router
from app.api.routes.autonomy import router as autonomy_router
from app.api.routes.baton_packets import router as baton_packets_router
from app.api.routes.compat import router as compat_router
from app.api.routes.context import router as context_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.diagnostics import router as diagnostics_router
from app.api.routes.health import router as health_router
from app.api.routes.memory import router as memory_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.project_events import router as project_events_router
from app.api.routes.routing import router as routing_router
from app.api.routes.runs import router as runs_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.workspaces import router as workspaces_router
from app.config import get_settings
from app.lifecycle import lifespan
from app.observability import configure_logging, request_observability_middleware
from app.security import create_security_middleware


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title="Agent Workforce Orchestrator", lifespan=lifespan)
    app.middleware("http")(create_security_middleware(settings))
    app.middleware("http")(request_observability_middleware)

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(tasks_router)
    app.include_router(workspaces_router)
    app.include_router(agent_runs_router)
    app.include_router(baton_packets_router)
    app.include_router(dashboard_router)
    app.include_router(project_events_router)
    app.include_router(routing_router)
    app.include_router(runs_router)
    app.include_router(memory_router)
    app.include_router(context_router)
    app.include_router(analyst_router)
    app.include_router(diagnostics_router)
    app.include_router(autonomy_router)
    app.include_router(compat_router)
    return app


app = create_app()
