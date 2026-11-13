# Singularity TypeScript MCP Gateway

Runtime: Node 24, official `@modelcontextprotocol/server` and Node HTTP adapter.
Plane remains the authorization and business-data authority. Five tools only;
repository reads remain Plane UI/API features. Bearers come only from HTTP headers.

From the repository root:

```sh
pnpm --filter @plane/mcp-gateway build
pnpm --filter @plane/mcp-gateway test
pnpm exec oxlint apps/mcp-gateway/src apps/mcp-gateway/tests-ts
node apps/mcp-gateway/dist/src/main.js
```

Build the Dockerfile with the **repository root** as context. The prior Python
image and `Dockerfile.python` are retained for rollback and compatibility tests;
Python is not in the new runtime. Configuration names and SQLite schema remain
unchanged. The new runtime exchanges a short-lived Plane token on each business
request rather than using the old encrypted token cache. All calls recheck grants.

Fernet-encrypted pending decisions and Python canonical fingerprints are preserved.
`tests/interop.py` and `tests-ts/interop.ts` verify both directions against a copied
SQLite fixture, including Unicode. Never delete decisions or replace the database
when switching images. Quiesce the Gateway and back up its SQLite volume and key
separately before rollout. The previous image can read new decisions as well.

Run `node dist/src/export-schema.js` inside this package after build to export
SDK tool schemas. Deployment, real-client acceptance, recovery and external gaps
are recorded in `docs/unified-platform-delivery.md` and the plane-ops runbook.
