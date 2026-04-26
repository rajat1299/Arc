.PHONY: test lint typecheck frontend verify

test:
	uv run pytest packages/opscanvas-core/tests -q

lint:
	uv run ruff check .

typecheck:
	uv run mypy packages/opscanvas-core/src

frontend:
	@if [ -f web/package.json ]; then \
		pnpm --dir web run verify; \
	else \
		echo "web/package.json not found; skipping frontend checks"; \
	fi

verify: test lint typecheck frontend
