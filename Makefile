.PHONY: test lint typecheck frontend smoke-ingest verify

test:
	uv run pytest packages/opscanvas-core/tests services/api/tests packages/opscanvas-agents/tests -q
	uv run pytest packages/opscanvas-claude/tests -q
	uv run pytest packages/opscanvas-langgraph/tests -q

lint:
	uv run ruff check packages services

typecheck:
	uv run mypy packages/opscanvas-core/src services/api/src packages/opscanvas-agents/src packages/opscanvas-claude/src packages/opscanvas-langgraph/src

frontend:
	@if [ -f web/package.json ]; then \
		pnpm --filter web lint && \
		pnpm --filter web typecheck; \
	else \
		echo "web/package.json not found; skipping frontend checks"; \
	fi

smoke-ingest:
	uv run python scripts/smoke_ingest.py

verify: test lint typecheck frontend
