.PHONY: up down restart logs build setup test test-backend typecheck-frontend clean help

help:
	@echo "VoIP SIP Analyzer — available commands:"
	@echo ""
	@echo "  make setup    - First-time setup (checks Docker, builds, starts everything)"
	@echo "  make up       - Start the stack (docker compose up -d)"
	@echo "  make down     - Stop the stack"
	@echo "  make restart  - Restart the stack"
	@echo "  make logs     - Follow logs from all containers"
	@echo "  make build    - Rebuild containers"
	@echo "  make test     - Run the backend test suite"
	@echo "  make clean    - Remove containers, volumes, and build artifacts"
	@echo ""

setup:
	./setup.sh

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

build:
	docker compose up --build -d

test: test-backend

test-backend:
	cd backend && pip install -q -r requirements.txt --break-system-packages 2>/dev/null || pip install -q -r requirements.txt; \
	pytest -v

typecheck-frontend:
	cd frontend && npm install --silent && npx tsc --noEmit

clean:
	docker compose down -v
	find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist frontend/node_modules
	rm -f backend/data/voip_analyzer.db
