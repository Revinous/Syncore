from fastapi import FastAPI

from app.api.routes.analyst import router as analyst_router
from app.api.routes.health import router as health_router
from app.lifecycle import lifespan
from app.observability import configure_logging, request_observability_middleware


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Agent Workforce Orchestrator", lifespan=lifespan)
    app.middleware("http")(request_observability_middleware)
    app.include_router(health_router)
    app.include_router(analyst_router)
    return app


app = create_app()
