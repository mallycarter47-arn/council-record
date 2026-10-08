# The Discord bot, with everything it needs to answer without a laptop:
# the Flue agent (Node), search.py (Python), and the SQLite index itself.
#
# search.py uses only the Python standard library. The daily alert run
# (scripts/alerts.py) also re-pulls eSCRIBE, which needs requests, and reads the
# clock in Detroit time, which needs tzdata — both from apt, no pip.
#
# The baked-in database is only a seed: on first boot it is copied to the Fly
# volume at /data, and from then on the bot searches, refreshes and stores
# alert subscriptions in that live copy.

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
    && apt-get install -y --no-install-recommends python3 python3-requests tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The frozen search path: these are copied in as-is and run exactly as they do
# on a laptop.
COPY scripts/ ./scripts/
COPY db/council_record.db db/schema.sql ./db/

COPY --from=build /app/agent/node_modules ./agent/node_modules
COPY --from=build /app/agent/dist ./agent/dist
COPY agent/package.json ./agent/package.json

ENV NODE_ENV=production \
    COUNCIL_ROOT=/app \
    COUNCIL_PYTHON=python3 \
    COUNCIL_DB=/data/council_record.db \
    COUNCIL_RAW=/data/raw \
    ALERTS_SCHEDULE=1 \
    PORT=8080

EXPOSE 8080
WORKDIR /app/agent
CMD ["sh", "-c", "mkdir -p /data/raw && { [ -f \"$COUNCIL_DB\" ] || cp /app/db/council_record.db \"$COUNCIL_DB\"; } && exec node dist/server.mjs"]
