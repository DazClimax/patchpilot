#!/bin/bash
# PatchPilot — Server Install Script
# Runs on any Debian/Ubuntu host (including Raspberry Pi, LXC containers)
# Usage: sudo bash install-server.sh [PORT=8443] [AGENT_PORT=8050]

set -e

HOST="0.0.0.0"
PORT="${PORT:-8443}"
AGENT_PORT="${AGENT_PORT:-8050}"
INSTALL_DIR="/opt/patchpilot"
VENV_DIR="/opt/patchpilot-venv"
SSL_DIR="$INSTALL_DIR/ssl"
SERVICE_USER="patchpilot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/var/log/patchpilot-install.log"
RUNTIME_LOG_DIR="/var/log/patchpilot"
BOOTSTRAP_ENV_FILE="/run/patchpilot-bootstrap.env"
BOOTSTRAP_PASSWORD_FILE="$INSTALL_DIR/bootstrap-admin.txt"

require_root() {
  if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    echo "[patchpilot] Please run install-server.sh as root." >&2
    echo "[patchpilot] Example: sudo bash install-server.sh" >&2
    exit 1
  fi
}

require_apt() {
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "[patchpilot] install-server.sh currently supports Debian/Ubuntu-style hosts with apt." >&2
    echo "[patchpilot] RPM support currently applies to managed clients/agents, not to the PatchPilot server installer." >&2
    exit 1
  fi
}

log_install() {
  mkdir -p "$(dirname "$LOG_FILE")"
  touch "$LOG_FILE"
  chmod 600 "$LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
}

step() {
  echo ""
  echo "[$1/8] $2"
}

require_root
require_apt
log_install

echo "=== PatchPilot Server Installation ==="
echo "Install dir  : $INSTALL_DIR"
echo "Venv         : $VENV_DIR"
echo "UI port      : $PORT (HTTPS)"
echo "Agent port   : $AGENT_PORT (HTTPS)"
echo "Log file     : $LOG_FILE"
echo "Runtime log  : $RUNTIME_LOG_DIR/server.log"

# Dependencies
step 1 "Installing server dependencies"
apt-get update -qq
apt-get install -y python3 python3-pip python3-venv openssl

# Create service user
step 2 "Ensuring dedicated service user exists"
if ! id "$SERVICE_USER" &>/dev/null; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  echo "Created system user: $SERVICE_USER"
else
  echo "System user already exists: $SERVICE_USER"
fi

# Install server files
step 3 "Copying PatchPilot files into place"
mkdir -p "$INSTALL_DIR/server" "$INSTALL_DIR/agent" "$SSL_DIR"
cp -r "$SCRIPT_DIR/server/"* "$INSTALL_DIR/server/"
cp -r "$SCRIPT_DIR/agent/"* "$INSTALL_DIR/agent/"
chmod +x "$INSTALL_DIR/server/start.sh"

# Copy pre-built frontend (if available)
if [ -d "$SCRIPT_DIR/frontend/dist" ]; then
  mkdir -p "$INSTALL_DIR/frontend"
  cp -r "$SCRIPT_DIR/frontend/dist" "$INSTALL_DIR/frontend/"
  echo "Frontend (pre-built) copied."
else
  echo "WARNING: No pre-built frontend found. Build it first with:"
  echo "  cd frontend && npm install && npm run build"
fi

# Python venv
step 4 "Creating Python virtual environment"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet -r "$INSTALL_DIR/server/requirements.txt"

# ── Generate self-signed SSL certificate (3 years) ───────────────────────────
step 5 "Preparing TLS certificate"
if [ ! -f "$SSL_DIR/cert.pem" ] || [ ! -f "$SSL_DIR/key.pem" ]; then
  echo "[patchpilot] Generating self-signed SSL certificate (3 years)..."
  HOSTNAME_IP="$(hostname -I | awk '{print $1}')"
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$SSL_DIR/key.pem" \
    -out "$SSL_DIR/cert.pem" \
    -days 1095 \
    -subj "/CN=PatchPilot" \
    -addext "subjectAltName=IP:${HOSTNAME_IP:-127.0.0.1},DNS:localhost" \
    2>/dev/null
  chmod 600 "$SSL_DIR/key.pem"
  chmod 644 "$SSL_DIR/cert.pem"
  echo "[patchpilot] SSL certificate generated at $SSL_DIR/"
else
  echo "[patchpilot] Existing SSL certificate found — keeping it."
fi

# Generate admin key (used for API auth and Fernet encryption of secrets)
ADMIN_KEY="$(openssl rand -hex 32)"
# Environment file (only create if missing — never overwrite existing config)
step 6 "Writing environment configuration"
if [ ! -f "$INSTALL_DIR/.env" ]; then
  cat > "$INSTALL_DIR/.env" <<EOF
PORT=$PORT
AGENT_PORT=$AGENT_PORT
AGENT_SSL=1
SSL_CERTFILE=$SSL_DIR/cert.pem
SSL_KEYFILE=$SSL_DIR/key.pem
PATCHPILOT_ADMIN_KEY=$ADMIN_KEY
EOF
  chmod 600 "$INSTALL_DIR/.env"
  echo "Created $INSTALL_DIR/.env (HTTPS enabled on both ports)"
else
  # Ensure PATCHPILOT_ADMIN_KEY exists (needed for Fernet encryption)
  if ! grep -q '^PATCHPILOT_ADMIN_KEY=' "$INSTALL_DIR/.env"; then
    echo "PATCHPILOT_ADMIN_KEY=$ADMIN_KEY" >> "$INSTALL_DIR/.env"
    echo "Added PATCHPILOT_ADMIN_KEY to existing .env"
  fi
  echo "Keeping existing $INSTALL_DIR/.env"
fi

# Fix ownership
step 7 "Fixing ownership and service permissions"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$VENV_DIR"
mkdir -p "$RUNTIME_LOG_DIR"
touch "$RUNTIME_LOG_DIR/server.log"
chown -R "$SERVICE_USER:$SERVICE_USER" "$RUNTIME_LOG_DIR"
chmod 750 "$RUNTIME_LOG_DIR"
chmod 640 "$RUNTIME_LOG_DIR/server.log"

# Install systemd service file
cp "$SCRIPT_DIR/patchpilot.service" /etc/systemd/system/patchpilot.service
cp "$SCRIPT_DIR/patchpilot.logrotate" /etc/logrotate.d/patchpilot

# Sudoers entry for service self-restart (needed for port/SSL changes from UI)
echo "$SERVICE_USER ALL=(root) NOPASSWD: /bin/systemctl restart patchpilot" > /etc/sudoers.d/patchpilot
chmod 440 /etc/sudoers.d/patchpilot

step 8 "Enabling and starting PatchPilot"
rm -f "$BOOTSTRAP_ENV_FILE"
if ! grep -q '^PATCHPILOT_ADMIN_PASSWORD=' "$INSTALL_DIR/.env" 2>/dev/null; then
  if [ -n "${PATCHPILOT_ADMIN_PASSWORD:-}" ]; then
    cat > "$BOOTSTRAP_ENV_FILE" <<EOF
PATCHPILOT_ADMIN_PASSWORD=$PATCHPILOT_ADMIN_PASSWORD
EOF
  else
    cat > "$BOOTSTRAP_ENV_FILE" <<EOF
PATCHPILOT_BOOTSTRAP_PASSWORD_FILE=$BOOTSTRAP_PASSWORD_FILE
EOF
  fi
  chmod 600 "$BOOTSTRAP_ENV_FILE"
fi
systemctl daemon-reload
systemctl enable patchpilot
systemctl restart patchpilot

if [ -f "$BOOTSTRAP_ENV_FILE" ]; then
  for _ in $(seq 1 20); do
    if [ -n "${PATCHPILOT_ADMIN_PASSWORD:-}" ] || [ -f "$BOOTSTRAP_PASSWORD_FILE" ]; then
      break
    fi
    sleep 1
  done
  rm -f "$BOOTSTRAP_ENV_FILE"
  if [ -f "$BOOTSTRAP_PASSWORD_FILE" ]; then
    chmod 600 "$BOOTSTRAP_PASSWORD_FILE"
    chown root:root "$BOOTSTRAP_PASSWORD_FILE"
  fi
fi

IP="$(hostname -I | awk '{print $1}')"
echo ""
echo "=== Installation complete! ==="
echo "Service    : systemctl status patchpilot"
echo "Logs       : journalctl -u patchpilot -f"
echo "File log   : tail -f $RUNTIME_LOG_DIR/server.log"
echo "Web UI     : https://${IP}:${PORT}"
echo "Agent API  : https://${IP}:${AGENT_PORT}"
echo "Install log: $LOG_FILE"
if [ -f "$BOOTSTRAP_PASSWORD_FILE" ]; then
  echo "Admin pass : sudo cat $BOOTSTRAP_PASSWORD_FILE"
fi
echo ""
echo "SSL is enabled by default with a self-signed certificate (3 years)."
echo "You can replace it with your own certificate in the Settings UI."
