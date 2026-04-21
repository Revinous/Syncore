from fastapi import FastAPI

app = FastAPI(title="Agent Workforce Orchestrator")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

