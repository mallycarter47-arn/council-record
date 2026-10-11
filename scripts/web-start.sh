#!/bin/sh
# Starts the public site on Fly with its own live copy of the council database.
#
# The database baked into the image is only a seed. It is copied to the volume
# on first boot, and again whenever a deploy ships a different one (a new
# Journal year, a parser fix). From then on the site refreshes that copy from
# eSCRIBE every 12 hours, the same way the bot's alert run does, so the site
# and the alerts show the same meetings.

set -e

SEED=/app/db/council_record.db
DB="$COUNCIL_DB"
mkdir -p "$(dirname "$DB")" "$COUNCIL_RAW"

seed=$(md5sum "$SEED" | cut -d' ' -f1)
if [ ! -f "$DB" ] || [ "$(cat "$DB.seed" 2>/dev/null)" != "$seed" ]; then
  echo "[start] seeding $DB from the image"
  rm -f "$DB-wal" "$DB-shm"
  cp "$SEED" "$DB.tmp"
  mv "$DB.tmp" "$DB"
  echo "$seed" > "$DB.seed"
fi

# Catch up on any meetings since the seed was built, re-pull the last two weeks
# and the next month (new agendas, minutes posted late), then the meeting box.
refresh() {
  python3 /app/scripts/ingest_escribe.py --quiet \
    && python3 /app/scripts/ingest_escribe.py --refresh 14 --quiet \
    && python3 /app/scripts/fetch_upcoming.py
}

(
  sleep 30
  while true; do
    if refresh > /tmp/refresh.log 2>&1; then
      echo "[refresh] ok: $(tail -1 /tmp/refresh.log)"
    else
      echo "[refresh] failed:"; tail -5 /tmp/refresh.log
    fi
    sleep 43200
  done
) &

exec npm run start -- -p 8080 -H 0.0.0.0
