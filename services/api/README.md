# OpsCanvas API

FastAPI service boundary for OpsCanvas ingest and query APIs.

Implemented routes:

- `GET /healthz` returns service status metadata.
- `POST /v1/ingest/runs` validates one canonical `opscanvas-core` `Run` payload and
  returns an accepted envelope with span and event counts.

This service currently performs in-memory validation only. It does not write to a
database, queue, redaction pipeline, auth layer, or pricing engine.
