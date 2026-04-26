.PHONY: bootstrap up down logs format lint test check backend-test frontend-test demo-local \
	install-local db-local-init dev-local bootstrap-local local-test

bootstrap:
	bash scripts/bootstrap.sh

install-local:
	bash scripts/install_local.sh

db-local-init:
	bash scripts/init_local_sqlite.sh

dev-local:
	bash scripts/dev_local.sh

bootstrap-local: install-local db-local-init

local-test:
	SYNCORE_DB_BACKEND=sqlite SQLITE_DB_PATH=.syncore/test.db REDIS_REQUIRED=false \
		bash scripts/init_local_sqlite.sh
	PYTHONPATH=services/orchestrator:. SYNCORE_DB_BACKEND=sqlite \
	SQLITE_DB_PATH=.syncore/test.db REDIS_REQUIRED=false \
	python3 -m pytest services/orchestrator/tests services/memory/tests -q

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

demo-local:
	bash scripts/demo_local_flow.sh

check: lint test
	npm --prefix apps/web run typecheck
	npm --prefix apps/web run build
