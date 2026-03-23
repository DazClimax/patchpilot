#!/bin/bash
# PatchPilot server startup — supports optional SSL
set -e

PORT="${PORT:-8000}"
SSL_CERTFILE="${SSL_CERTFILE:-}"
SSL_KEYFILE="${SSL_KEYFILE:-}"

ARGS="app:app --host 0.0.0.0 --port $PORT"

if [ -n "$SSL_CERTFILE" ] && [ -n "$SSL_KEYFILE" ]; then
    echo "[patchpilot] Starting with SSL (cert=$SSL_CERTFILE)"
    ARGS="$ARGS --ssl-certfile $SSL_CERTFILE --ssl-keyfile $SSL_KEYFILE"
else
    echo "[patchpilot] Starting without SSL (plain HTTP)"
fi

exec /opt/patchpilot-venv/bin/uvicorn $ARGS
