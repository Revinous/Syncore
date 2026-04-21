from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.lifecycle import lifespan


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Workforce Orchestrator", lifespan=lifespan)
    app.include_router(health_router)
    return app


app = create_app()
