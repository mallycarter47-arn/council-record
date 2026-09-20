# The Discord bot, with everything it needs to answer without a laptop:
# the Flue agent (Node), search.py (Python), and the SQLite index itself.
#
# search.py uses only the Python standard library, so there is nothing to pip
# install — python3 and the database file are the whole runtime dependency.

FROM node:24-slim AS build

WORKDIR /app/agent
COPY agent/package.json agent/package-lock.json ./
RUN npm ci
COPY agent/tsconfig.json agent/vite.config.ts agent/flue.config.ts ./
COPY agent/src ./src
RUN npm run build

# ---------------------------------------------------------------------------

FROM node:24-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The frozen search path: these are copied in as-is and run exactly as they do
# on a laptop.
COPY scripts/ ./scripts/
COPY db/council_record.db ./db/council_record.db

COPY --from=build /app/agent/node_modules ./agent/node_modules
COPY --from=build /app/agent/dist ./agent/dist
COPY agent/package.json ./agent/package.json

ENV NODE_ENV=production \
    COUNCIL_ROOT=/app \
    COUNCIL_PYTHON=python3 \
    PORT=8080

EXPOSE 8080
WORKDIR /app/agent
CMD ["node", "dist/server.mjs"]
