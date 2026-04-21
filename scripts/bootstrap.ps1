Copy-Item .env.example .env -ErrorAction SilentlyContinue

docker compose up -d postgres redis

Write-Host "Waiting for PostgreSQL to become available..."
do {
  Start-Sleep -Seconds 2
  docker exec agent-postgres pg_isready -U agentos | Out-Null
} until ($LASTEXITCODE -eq 0)

Write-Host "PostgreSQL is ready."

docker compose up -d --build orchestrator web
docker compose ps

