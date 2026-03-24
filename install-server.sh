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

echo "=== PatchPilot Server Installation ==="
echo "Install dir  : $INSTALL_DIR"
echo "Venv         : $VENV_DIR"
echo "UI port      : $PORT (HTTPS)"
echo "Agent port   : $AGENT_PORT (HTTPS)"

# Dependencies
apt-get update -qq
apt-get install -y python3 python3-pip python3-venv openssl

# Create service user
if ! id "$SERVICE_USER" &>/dev/null; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  echo "Created system user: $SERVICE_USER"
fi

# Install server files
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
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet -r "$INSTALL_DIR/server/requirements.txt"

# ── Generate self-signed SSL certificate (3 years) ───────────────────────────
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

# Environment file (only create if missing — never overwrite existing config)
if [ ! -f "$INSTALL_DIR/.env" ]; then
  cat > "$INSTALL_DIR/.env" <<EOF
PORT=$PORT
AGENT_PORT=$AGENT_PORT
AGENT_SSL=1
SSL_CERTFILE=$SSL_DIR/cert.pem
SSL_KEYFILE=$SSL_DIR/key.pem
EOF
  chmod 600 "$INSTALL_DIR/.env"
  echo "Created $INSTALL_DIR/.env (HTTPS enabled on both ports)"
else
  echo "Keeping existing $INSTALL_DIR/.env"
fi

# Fix ownership
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$VENV_DIR"

# Install systemd service file
cp "$SCRIPT_DIR/patchpilot.service" /etc/systemd/system/patchpilot.service

# Sudoers entry for service self-restart (needed for port/SSL changes from UI)
echo "$SERVICE_USER ALL=(root) NOPASSWD: /bin/systemctl restart patchpilot" > /etc/sudoers.d/patchpilot
chmod 440 /etc/sudoers.d/patchpilot

systemctl daemon-reload
systemctl enable patchpilot
systemctl restart patchpilot

IP="$(hostname -I | awk '{print $1}')"
echo ""
echo "=== Installation complete! ==="
echo "Service    : systemctl status patchpilot"
echo "Logs       : journalctl -u patchpilot -f"
echo "Web UI     : https://${IP}:${PORT}"
echo "Agent API  : https://${IP}:${AGENT_PORT}"
echo ""
echo "SSL is enabled by default with a self-signed certificate (3 years)."
echo "You can replace it with your own certificate in the Settings UI."
