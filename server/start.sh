#!/bin/bash
# PatchPilot server startup — dual-port with independent SSL per port
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8443}"
AGENT_PORT="${AGENT_PORT:-8050}"
SSL_CERTFILE="${SSL_CERTFILE:-}"
SSL_KEYFILE="${SSL_KEYFILE:-}"
AGENT_SSL="${AGENT_SSL:-}"

UVICORN="${PATCHPILOT_UVICORN_BIN:-/opt/patchpilot-venv/bin/uvicorn}"
if [ ! -x "$UVICORN" ]; then
    UVICORN="$(command -v uvicorn)"
fi

cd "$SCRIPT_DIR"

# ── UI process ────────────────────────────────────────────────────────────────
UI_ARGS="app:app --host 0.0.0.0 --port $PORT"
if [ -n "$SSL_CERTFILE" ] && [ -n "$SSL_KEYFILE" ]; then
    echo "[patchpilot] UI port $PORT (HTTPS)"
    UI_ARGS="$UI_ARGS --ssl-certfile $SSL_CERTFILE --ssl-keyfile $SSL_KEYFILE"
else
    echo "[patchpilot] UI port $PORT (HTTP)"
fi

# ── Agent process ─────────────────────────────────────────────────────────────
AGENT_ARGS="app:app --host 0.0.0.0 --port $AGENT_PORT"
if [ "$AGENT_SSL" = "1" ] && [ -n "$SSL_CERTFILE" ] && [ -n "$SSL_KEYFILE" ]; then
    echo "[patchpilot] Agent port $AGENT_PORT (HTTPS)"
    AGENT_ARGS="$AGENT_ARGS --ssl-certfile $SSL_CERTFILE --ssl-keyfile $SSL_KEYFILE"
else
    echo "[patchpilot] Agent port $AGENT_PORT (HTTP)"
fi

# ── Launch both, kill sibling on exit ─────────────────────────────────────────
cleanup() {
    echo "[patchpilot] Shutting down..."
    kill $UI_PID $AGENT_PID 2>/dev/null || true
    wait $UI_PID $AGENT_PID 2>/dev/null || true
}
trap cleanup EXIT TERM INT

# If UI and Agent port are the same, run single process (backward compat)
if [ "$PORT" = "$AGENT_PORT" ]; then
    echo "[patchpilot] Single-port mode (UI + Agent on $PORT)"
    exec $UVICORN $UI_ARGS
fi

$UVICORN $UI_ARGS &
UI_PID=$!

$UVICORN $AGENT_ARGS &
AGENT_PID=$!

# Wait for either to exit, then kill the other
wait -n $UI_PID $AGENT_PID 2>/dev/null
EXIT_CODE=$?
echo "[patchpilot] A process exited (code=$EXIT_CODE), stopping both..."
exit $EXIT_CODE
