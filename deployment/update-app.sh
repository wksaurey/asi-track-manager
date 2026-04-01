#!/usr/bin/env bash
# update-app.sh — Pull latest code from main and rebuild
# Can be triggered manually, by webhook, or by scheduled polling

set -e

APP_DIR="$HOME/apps/asi-track-manager"

echo "$(date) — Starting update..."

cd "$APP_DIR"

git pull origin main || { echo "ERROR: git pull failed — aborting update" >&2; exit 1; }

# Rebuild and restart (--no-cache ensures fresh pip install if requirements changed)
docker compose build --no-cache
docker compose up -d

# Run migrations in case the update added new ones
docker compose exec web python3 manage.py migrate --noinput

echo "$(date) — Update complete!"
