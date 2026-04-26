# Postgres

Postgres is the local metadata store for OpsCanvas. It owns state that benefits
from relational constraints and transactions:

- orgs, projects, and environments
- API key metadata and key hashes
- budget policies
- eval dataset metadata
- prompt versions

Start it locally with:

```bash
docker compose -f infra/docker-compose.dev.yml up postgres
```

`001_metadata.sql` is mounted read-only into the Postgres container and runs
during first database initialization. Delete the `postgres_data` Docker volume
to re-run it from scratch in local development.

Design notes:

- API keys store `key_hash` and a non-secret `prefix`; raw keys are never stored.
- `projects.capture_inputs` and `projects.capture_outputs` are early
  data-minimization controls for future ingestion.
- Budget policies capture the v1 cap shapes: monthly, per-run, and per-tenant.
- Eval datasets and prompt versions include explicit version/config fields, but
  the actual eval item and cassette formats are outside this task.
- Runtime run/span/event payloads do not belong here; they are stored in
  ClickHouse.
