# Infrastructure

Local development infrastructure and schema artifacts for OpsCanvas.

## Local services

```bash
docker compose -f infra/docker-compose.dev.yml up
```

The compose file starts:

- ClickHouse on HTTP `8123` and native `9000`
- Postgres on `5432`
- Redis on `6379`

Credentials are intentionally local-dev only:

- database/user: `opscanvas`
- password: `opscanvas_dev_password`

## Storage split

- ClickHouse stores wide runtime analytics: `runs`, `spans`, `span_events`, and
  `scores`.
- Postgres stores metadata and relational state: orgs, projects, environments,
  API key hashes, budget policies, eval datasets, prompt versions, and the
  initial model pricing table format for the future cost engine.
- Redis is only a queue/cache/rate-limit placeholder. It is not a durable domain
  store.

The SQL files are plain local-dev seeds, not a migration framework. They are
mounted read-only into the database containers and run on first initialization
of the Docker volumes.
