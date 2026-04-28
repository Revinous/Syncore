# Troubleshooting

## API connection refused

- Ensure orchestrator is running on `:8000`
- Native: `make dev-local`
- Docker: `make bootstrap`

## CLI works but Web UI fails

- Check `NEXT_PUBLIC_API_BASE_URL`
- Verify CORS and API port

## TUI opens but no data

- Run `syncore status`
- Confirm workspace/task records exist
- Check `/diagnostics` and `/diagnostics/routes`
