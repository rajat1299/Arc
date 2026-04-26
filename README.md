# Arc

Engineering home for the Arc surface in the OpsCanvas -> Arc -> Atrium stack.

This repository is currently a foundation scaffold for shared OpsCanvas/Arc
tooling. It provides the monorepo layout, deterministic Python commands, and
placeholder package/service/app directories. It does not yet implement product
behavior, ingest APIs, storage schemas, or a frontend app.

## Layout

- `packages/opscanvas-core/`: shared Python package, currently version-only.
- `packages/opscanvas-agents/`: placeholder for the future OpenAI Agents plugin.
- `services/api/`: placeholder for the future hosted API service.
- `web/`: placeholder for the future Next.js app.
- `infra/`: placeholder for future local development infrastructure.

## Local Docs Policy

Local `docs/` is gitignored here. Keep product and engineering specs in that
directory on your machine or share them out of band. Do not commit local-only
reference docs to this repository.

## First Commands

Install and verify the Python workspace:

```sh
uv sync --all-packages
make verify
```

Useful focused commands:

```sh
uv run pytest packages/opscanvas-core/tests -q
uv run ruff check .
uv run mypy packages/opscanvas-core/src
pnpm run verify
```

## Repository

- Remote: <https://github.com/rajat1299/Arc>
