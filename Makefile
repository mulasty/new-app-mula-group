SHELL := /bin/sh

.PHONY: install-dev seed test lint format dashboard-install dashboard-build dashboard-lint dashboard-test smoke preflight deploy-staging deploy-prod

install-dev:
	cd backend && pip install -r requirements.txt -r requirements-dev.txt

seed:
	cd backend && python scripts/seed_dev_data.py

test:
	cd backend && pytest -q

lint:
	cd backend && ruff check . && black --check . && isort --check-only .

format:
	cd backend && ruff check . --fix && black . && isort .

dashboard-install:
	cd dashboard && npm install

dashboard-build:
	cd dashboard && npm run build

dashboard-lint:
	cd dashboard && npm run lint

dashboard-test:
	cd dashboard && npm run build

smoke:
	sh scripts/smoke_all.sh

preflight:
	sh scripts/preflight_check.sh

deploy-staging:
	bash scripts/deploy.sh staging

deploy-prod:
	bash scripts/deploy.sh production
