# Web

Minimal Next.js shell for the Arc/OpsCanvas trace operations workspace.

## Data Boundary

The shell reads `OPSCANVAS_API_BASE_URL` on the server and fetches
`/v1/runs` when it is set. If the API is not configured, unavailable, returns
an error, or returns an unexpected payload shape, the page falls back to static
mock data from `web/app/data.ts` so the first screen remains usable.

## Commands

- `pnpm --filter web dev`
- `pnpm --filter web build`
- `pnpm --filter web lint`
- `pnpm --filter web typecheck`
