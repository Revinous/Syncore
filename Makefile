bootstrap:
	bash scripts/bootstrap.sh

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

test:
	echo "Tests will be added by Codex in Phase 1"

