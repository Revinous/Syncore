# Getting Started

## Native (Solo Developer)

1. `cp .env.example .env`
2. `make bootstrap-local`
3. `make dev-local`
4. Open `http://localhost:3000`
5. Verify API: `curl http://localhost:8000/health`

## Docker (Enterprise Topology)

1. `cp .env.example .env`
2. `make bootstrap`
3. Open `http://localhost:3000`
4. Verify API: `curl http://localhost:8000/health`

## CLI/TUI Quick Start

1. `make install-cli`
2. `syncore status`
3. `syncore workspace add ./my-project --name my-project`
4. `syncore open my-project`
