# Redis

Redis is included only as a local development placeholder for ephemeral
infrastructure:

- ingestion queues or short-lived buffers
- rate-limit counters
- query/API caches
- pub/sub for local worker experiments

No durable OpsCanvas domain state should be modeled in Redis. Canonical runtime
analytics belong in ClickHouse, and metadata/org/project/policy/eval/prompt
state belongs in Postgres.

Start it locally with:

```bash
docker compose -f infra/docker-compose.dev.yml up redis
```
