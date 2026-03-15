.PHONY: help install install-dev lint format typecheck test test-one run-agent run-mcp run-agent-demo publish publish-demo clean

# ── Help ──────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  AI News Agent — команды управления проектом"
	@echo ""
	@echo "  Зависимости:"
	@echo "    make install          Установить зависимости из requirements.txt"
	@echo "    make install-dev      Установить зависимости + ruff, mypy"
	@echo ""
	@echo "  Качество кода:"
	@echo "    make lint             Проверить стиль кода (ruff)"
	@echo "    make format           Отформатировать код (ruff)"
	@echo "    make typecheck        Проверить типы (mypy)"
	@echo ""
	@echo "  Тесты:"
	@echo "    make test             Запустить все тесты"
	@echo "    make test-one T=...   Запустить один тест (T=путь::Класс::метод)"
	@echo ""
	@echo "  Запуск:"
	@echo "    make run-mcp          Запустить MCP SSE сервер (localhost:8000)"
	@echo "    make run-agent MSG=.. Запустить агент с сообщением (без публикации)"
	@echo "    make run-agent-demo   Демо-запрос без публикации"
	@echo "    make publish MSG=..   Сгенерировать и опубликовать пост в Telegram"
	@echo "    make publish-demo     Демо-запрос с публикацией в Telegram"
	@echo ""
	@echo "  Очистка:"
	@echo "    make clean            Удалить chroma_db, sessions.db, кэши"
	@echo ""

# ── Dependencies ──────────────────────────────────────────────────────────────

install:
	pip install -r requirements.txt

install-dev: install
	pip install ruff mypy

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	pytest tests/ -v

test-one:
	@test -n "$(T)" || (echo "Usage: make test-one T=tests/test_validator.py::TestInjectionDetection::test_clean_request_passes" && exit 1)
	pytest $(T) -v

# ── Run ───────────────────────────────────────────────────────────────────────

run-mcp:
	python -m src.mcp_server.server

run-agent:
	@test -n "$(MSG)" || (echo "Usage: make run-agent MSG='ваш запрос'" && exit 1)
	python -m src.main --message "$(MSG)"

run-agent-demo:
	python -m src.main --message "дай новости по AI и Python"

# ── Publish ───────────────────────────────────────────────────────────────────

_check-telegram-env:
	@token=$$(grep -E '^TELEGRAM_BOT_TOKEN=.+' .env 2>/dev/null | cut -d= -f2-); \
	channel=$$(grep -E '^TELEGRAM_PUBLISH_CHANNEL=.+' .env 2>/dev/null | cut -d= -f2-); \
	if [ -z "$$token" ]; then \
		echo "⚠️  TELEGRAM_BOT_TOKEN не задан в .env"; \
		echo "   Получите токен у @BotFather и добавьте бота администратором в канал."; \
		exit 1; \
	fi; \
	if [ -z "$$channel" ]; then \
		echo "⚠️  TELEGRAM_PUBLISH_CHANNEL не задан в .env"; \
		echo "   Укажите @username канала или числовой ID (например: -1001234567890)."; \
		exit 1; \
	fi

publish: _check-telegram-env
	@test -n "$(MSG)" || (echo "Usage: make publish MSG='ваш запрос'" && exit 1)
	python -m src.main --message "$(MSG)" --publish

publish-demo: _check-telegram-env
	python -m src.main --message "дай новости по AI и Python" --publish

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	rm -rf chroma_db/ sessions.db .pytest_cache __pycache__ src/**/__pycache__ tests/__pycache__
	find . -name "*.pyc" -delete
