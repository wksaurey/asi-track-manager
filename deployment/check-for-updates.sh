#!/usr/bin/env bash
# check-for-updates.sh — Poll GitHub for new commits on main
# Schedule to run every 5 minutes via cron (see DEPLOYMENT.md Section 7)

APP_DIR="$HOME/apps/asi-track-manager"
cd "$APP_DIR"

git fetch origin main

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "$(date) — New commits detected (local: $LOCAL, remote: $REMOTE). Updating..."
    "$APP_DIR/update-app.sh"
else
    echo "$(date) — No changes. Current commit: $LOCAL"
fi
