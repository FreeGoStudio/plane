FROM node:24.15.0-bookworm-slim AS build
RUN corepack enable && corepack prepare pnpm@11.10.0 --activate
WORKDIR /source
COPY pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/mcp-gateway/package.json apps/mcp-gateway/package.json
RUN pnpm install --filter @plane/mcp-gateway --frozen-lockfile --ignore-scripts
COPY apps/mcp-gateway/src apps/mcp-gateway/src
COPY apps/mcp-gateway/tsconfig.json apps/mcp-gateway/tsconfig.json
RUN pnpm --filter @plane/mcp-gateway build && pnpm --filter @plane/mcp-gateway deploy --legacy --prod /out
FROM node:24.15.0-bookworm-slim
WORKDIR /app
COPY --from=build /out ./
CMD ["node", "dist/src/main.js"]
