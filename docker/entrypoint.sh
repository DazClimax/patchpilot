#!/bin/sh
set -eu

PATCHPILOT_DATA_DIR="${PATCHPILOT_DATA_DIR:-/data}"
PATCHPILOT_DB_PATH="${PATCHPILOT_DB_PATH:-$PATCHPILOT_DATA_DIR/patchpilot.db}"
PATCHPILOT_ENV_FILE="${PATCHPILOT_ENV_FILE:-$PATCHPILOT_DATA_DIR/patchpilot.env}"
PATCHPILOT_SSL_DIR="${PATCHPILOT_SSL_DIR:-$PATCHPILOT_DATA_DIR/ssl}"

export PATCHPILOT_DATA_DIR PATCHPILOT_DB_PATH PATCHPILOT_ENV_FILE PATCHPILOT_SSL_DIR
export PATCHPILOT_RESTART_MODE="${PATCHPILOT_RESTART_MODE:-process}"
export PATCHPILOT_UVICORN_BIN="${PATCHPILOT_UVICORN_BIN:-uvicorn}"

PORT="${PORT:-8443}"
AGENT_PORT="${AGENT_PORT:-8050}"
AGENT_SSL="${AGENT_SSL:-1}"
PATCHPILOT_ALLOWED_ORIGINS="${PATCHPILOT_ALLOWED_ORIGINS:-http://localhost:5173,http://localhost:8000}"
INITIAL_ADMIN_PASSWORD_PRINTED=0

mkdir -p "$PATCHPILOT_DATA_DIR" "$PATCHPILOT_SSL_DIR"
touch "$PATCHPILOT_ENV_FILE"
chmod 600 "$PATCHPILOT_ENV_FILE"
chown -R patchpilot:patchpilot "$PATCHPILOT_DATA_DIR"

ensure_env_key() {
  key="$1"
  value="$2"
  if ! grep -q "^${key}=" "$PATCHPILOT_ENV_FILE" 2>/dev/null; then
    printf '%s=%s\n' "$key" "$value" >> "$PATCHPILOT_ENV_FILE"
  fi
}

replace_env_key() {
  key="$1"
  value="$2"
  tmp="${PATCHPILOT_ENV_FILE}.tmp"
  awk -F= -v k="$key" -v v="$value" '
    BEGIN { done=0 }
    $1 == k { print k "=" v; done=1; next }
    { print $0 }
    END { if (!done) print k "=" v }
  ' "$PATCHPILOT_ENV_FILE" > "$tmp"
  mv "$tmp" "$PATCHPILOT_ENV_FILE"
}

if ! grep -q '^PATCHPILOT_ADMIN_KEY=' "$PATCHPILOT_ENV_FILE" 2>/dev/null; then
  ensure_env_key "PATCHPILOT_ADMIN_KEY" "$(openssl rand -hex 32)"
fi

if [ -z "${PATCHPILOT_ADMIN_PASSWORD:-}" ] && ! grep -q '^PATCHPILOT_ADMIN_PASSWORD=' "$PATCHPILOT_ENV_FILE" 2>/dev/null; then
  GENERATED_ADMIN_PASSWORD="$(openssl rand -base64 18 | tr -d '\n' | tr '/+' '_-')"
  ensure_env_key "PATCHPILOT_ADMIN_PASSWORD" "$GENERATED_ADMIN_PASSWORD"
  INITIAL_ADMIN_PASSWORD_PRINTED=1
else
  GENERATED_ADMIN_PASSWORD=""
fi

ensure_env_key "PORT" "$PORT"
ensure_env_key "AGENT_PORT" "$AGENT_PORT"
ensure_env_key "AGENT_SSL" "$AGENT_SSL"
ensure_env_key "PATCHPILOT_ALLOWED_ORIGINS" "$PATCHPILOT_ALLOWED_ORIGINS"

if [ -n "${PATCHPILOT_ADMIN_PASSWORD:-}" ]; then
  replace_env_key "PATCHPILOT_ADMIN_PASSWORD" "$PATCHPILOT_ADMIN_PASSWORD"
fi

set -a
. "$PATCHPILOT_ENV_FILE"
set +a

if [ "${AGENT_SSL:-1}" = "1" ]; then
  if [ ! -f "$PATCHPILOT_SSL_DIR/cert.pem" ] || [ ! -f "$PATCHPILOT_SSL_DIR/key.pem" ]; then
    HOST_IP="$(hostname -i 2>/dev/null | awk '{print $1}')"
    [ -n "$HOST_IP" ] || HOST_IP="127.0.0.1"
    openssl req -x509 -newkey rsa:2048 -nodes \
      -keyout "$PATCHPILOT_SSL_DIR/key.pem" \
      -out "$PATCHPILOT_SSL_DIR/cert.pem" \
      -days 1095 \
      -subj "/CN=PatchPilot" \
      -addext "subjectAltName=IP:${HOST_IP},DNS:localhost" \
      >/dev/null 2>&1
    chmod 600 "$PATCHPILOT_SSL_DIR/key.pem"
    chmod 644 "$PATCHPILOT_SSL_DIR/cert.pem"
  fi
  replace_env_key "SSL_CERTFILE" "$PATCHPILOT_SSL_DIR/cert.pem"
  replace_env_key "SSL_KEYFILE" "$PATCHPILOT_SSL_DIR/key.pem"
else
  replace_env_key "SSL_CERTFILE" ""
  replace_env_key "SSL_KEYFILE" ""
fi

set -a
. "$PATCHPILOT_ENV_FILE"
set +a

echo "[patchpilot-docker] Data dir : $PATCHPILOT_DATA_DIR"
echo "[patchpilot-docker] DB path  : $PATCHPILOT_DB_PATH"
echo "[patchpilot-docker] Env file : $PATCHPILOT_ENV_FILE"
echo "[patchpilot-docker] SSL dir  : $PATCHPILOT_SSL_DIR"
echo "[patchpilot-docker] UI port  : ${PORT}"
echo "[patchpilot-docker] Agent    : ${AGENT_PORT}"
if [ "$INITIAL_ADMIN_PASSWORD_PRINTED" = "1" ]; then
  echo "[patchpilot-docker] Initial admin credentials:"
  echo "[patchpilot-docker]   username: admin"
  echo "[patchpilot-docker]   password: ${GENERATED_ADMIN_PASSWORD}"
  echo "[patchpilot-docker] Save this password now. It is only auto-generated on first startup with an empty data volume."
fi

exec gosu patchpilot /opt/patchpilot/server/start.sh
