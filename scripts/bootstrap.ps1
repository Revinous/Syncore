Copy-Item .env.example .env -ErrorAction SilentlyContinue

docker compose up -d --build postgres redis

Write-Host "Waiting for PostgreSQL to become available..."
do {
  Start-Sleep -Seconds 2
  docker exec agent-postgres pg_isready -U agentos | Out-Null
} until ($LASTEXITCODE -eq 0)

Write-Host "PostgreSQL is ready."
Write-Host "Applying database initialization/migration script..."
Get-Content scripts/init_db.sql | docker exec -i agent-postgres psql -U agentos -d agentos

docker compose up -d --build orchestrator web

Write-Host "Waiting for orchestrator health endpoint..."
do {
  Start-Sleep -Seconds 2
  curl.exe -fsS "http://localhost:8000/health" | Out-Null
} until ($LASTEXITCODE -eq 0)

Write-Host "Orchestrator is healthy."

docker compose ps
