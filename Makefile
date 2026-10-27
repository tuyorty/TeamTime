# xTime — частые команды. `make help` покажет список.
SHELL := /bin/bash
.DEFAULT_GOAL := help

PY      := backend/.venv/bin/python
BACKEND := cd backend && export PYTHONPATH=src &&
WEB     := cd frontend &&
COMPOSE := docker compose
TEST_DB ?= postgresql+asyncpg://teamtime:teamtime@localhost:5433/teamtime_test

.PHONY: help
help: ## Показать команды
	@awk 'BEGIN{FS=":.*##"} /^[a-zA-Z_-]+:.*##/{printf "  \033[36m%-16s\033[0m %s\n",$$1,$$2}' $(MAKEFILE_LIST)

# --- установка ---------------------------------------------------------------
.PHONY: install
install: ## Поставить зависимости бэкенда и фронтенда локально
	python3.12 -m venv backend/.venv
	backend/.venv/bin/pip install -e "backend[dev]"
	$(WEB) npm ci

# --- docker ------------------------------------------------------------------
.PHONY: up down logs demo reset
up: ## Поднять всё (db, api, bot, web)
	$(COMPOSE) up -d --build
	@echo "Сайт: http://localhost:$${WEB_PORT:-8080}"

down: ## Остановить контейнеры
	$(COMPOSE) down

logs: ## Логи api и bot
	$(COMPOSE) logs -f api bot

demo: ## Загрузить демо-данные в запущенный стек
	$(COMPOSE) exec api teamtime demo seed --force

reset: ## Удалить контейнеры вместе с базой
	$(COMPOSE) down -v

# --- разработка --------------------------------------------------------------
.PHONY: dev-db dev-api dev-web
dev-db: ## Поднять только PostgreSQL (порт 5433) для локальной разработки и тестов
	docker run -d --rm --name teamtime-dev-db -e POSTGRES_USER=teamtime -e POSTGRES_PASSWORD=teamtime \
	  -e POSTGRES_DB=teamtime -p 5433:5432 postgres:16-alpine
	@sleep 3
	docker exec teamtime-dev-db createdb -U teamtime teamtime_test || true

DEV_DB := postgresql+asyncpg://teamtime:teamtime@localhost:5433/teamtime

dev-api: ## API с демо-данными (миграции и seed при пустой базе)
	$(BACKEND) export DATABASE_URL=$(DEV_DB) DEMO=1 && .venv/bin/teamtime db upgrade \
	  && .venv/bin/teamtime demo seed --if-empty && .venv/bin/uvicorn teamtime.api.app:app --reload --reload-dir src

dev-web: ## Фронтенд с HMR
	$(WEB) npm run dev

# --- качество ----------------------------------------------------------------
.PHONY: lint typecheck test test-backend test-web e2e screenshots check
lint: ## Линтеры
	$(BACKEND) .venv/bin/ruff check . && .venv/bin/ruff format --check .
	$(WEB) npm run lint

typecheck: ## Проверка типов
	$(BACKEND) .venv/bin/mypy
	$(WEB) npm run typecheck

test-backend: ## Тесты бэкенда (нужна БД: make dev-db)
	$(BACKEND) TEST_DATABASE_URL=$(TEST_DB) .venv/bin/pytest --cov

test-web: ## Юнит-тесты фронтенда
	$(WEB) npm test

test: test-backend test-web ## Все тесты

e2e: ## Playwright-смоуки (нужен поднятый стек с DEMO=1)
	$(WEB) npm run e2e

screenshots: ## Скриншоты для README (нужен стек с DEMO=1)
	$(WEB) npm run screenshots

check: lint typecheck test ## Всё, что делает CI

# --- сервер ------------------------------------------------------------------
# Релиз — один архив: образы под архитектуру сервера + deploy/. Серверу не нужен интернет,
# кроме api.telegram.org для бота. Подробности — deploy/README.md.
VERSION  ?= $(shell git describe --tags --always --dirty 2>/dev/null || date +%Y%m%d%H%M)
PLATFORM ?= linux/amd64
HOST     ?=
DEST     ?= /opt/xtime
RELEASE  := dist/xtime-$(VERSION)

.PHONY: release deploy
release: ## Собрать архив для сервера: make release [PLATFORM=linux/arm64]
	docker buildx build --platform $(PLATFORM) --load -t xtime-backend:$(VERSION) -t xtime-backend:current backend
	docker buildx build --platform $(PLATFORM) --load -t xtime-web:$(VERSION) -t xtime-web:current frontend
	docker buildx build --platform $(PLATFORM) --load -t xtime-db:$(VERSION) -t xtime-db:current -f deploy/db.Dockerfile deploy
	rm -rf $(RELEASE) && mkdir -p $(RELEASE)
	cp deploy/docker-compose.yml deploy/.env.example deploy/install.sh deploy/backup.sh deploy/README.md \
	  deploy/xtime-tg-tunnel.service $(RELEASE)/
	echo $(VERSION) > $(RELEASE)/VERSION
	docker save xtime-backend:$(VERSION) xtime-backend:current xtime-web:$(VERSION) xtime-web:current \
	  xtime-db:$(VERSION) xtime-db:current | gzip > $(RELEASE)/images.tar.gz
	tar -C dist -czf $(RELEASE).tar.gz xtime-$(VERSION)
	@echo "Готово: $(RELEASE).tar.gz ($$(du -h $(RELEASE).tar.gz | cut -f1))"

deploy: release ## Собрать и установить на сервер: make deploy HOST=user@сервер
	@test -n "$(HOST)" || { echo "Укажите HOST=user@сервер"; exit 1; }
	scp $(RELEASE).tar.gz $(HOST):/tmp/
	ssh -t $(HOST) 'cd /tmp && tar -xzf xtime-$(VERSION).tar.gz && sudo ./xtime-$(VERSION)/install.sh $(DEST); rm -rf /tmp/xtime-$(VERSION) /tmp/xtime-$(VERSION).tar.gz'
