.PHONY: bootstrap up down logs format lint test check backend-test frontend-test

bootstrap:
	bash scripts/bootstrap.sh

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

format:
	python3 -m ruff format services/orchestrator services/router services/memory services/analyst packages/contracts/python

lint:
	python3 -m ruff check services/orchestrator services/router services/memory services/analyst packages/contracts/python
	npm --prefix apps/web run lint

test: backend-test frontend-test

backend-test:
	PYTHONPATH=services/orchestrator:. python3 -m pytest \
		services/orchestrator/tests \
		services/router/tests \
		services/memory/tests \
		services/analyst/tests \
		packages/contracts/python/test_models.py

frontend-test:
	npm --prefix apps/web run test:smoke

check: lint test
	npm --prefix apps/web run typecheck
	npm --prefix apps/web run build
