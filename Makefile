.PHONY: install lint test up down logs migrate sync delivery backup restore

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check app tests
	python -m compileall -q app tests migrations

test:
	pytest

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f app worker

migrate:
	docker compose run --rm migrate

sync:
	docker compose exec app python -m app.cli sync-catalog

delivery:
	docker compose exec worker python -m app.cli delivery-run

backup:
	mkdir -p backups
	docker compose exec -T db pg_dump -U pokemon_daily -d pokemon_daily -Fc > backups/pokemon_daily.dump

restore:
	test -n "$(FILE)"
	docker compose exec -T db pg_restore -U pokemon_daily -d pokemon_daily --clean --if-exists < "$(FILE)"

