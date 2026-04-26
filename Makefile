.PHONY: test lint typecheck frontend verify

test:
	uv run pytest packages/opscanvas-core/tests services/api/tests packages/opscanvas-agents/tests -q

lint:
	uv run ruff check packages services

typecheck:
	uv run mypy packages/opscanvas-core/src services/api/src packages/opscanvas-agents/src

frontend:
	@if [ -f web/package.json ]; then \
		pnpm --filter web lint && \
		pnpm --filter web typecheck; \
	else \
		echo "web/package.json not found; skipping frontend checks"; \
	fi

verify: test lint typecheck frontend
