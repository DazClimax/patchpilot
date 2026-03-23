#!/bin/bash
# PatchPilot — Server Install Script
# Runs on the Raspberry Pi (or any Debian/Ubuntu host)
# Usage: sudo bash install-server.sh [--host 0.0.0.0] [--port 8000]

set -e

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
INSTALL_DIR="/opt/patchpilot"
SERVICE_USER="patchpilot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== PatchPilot Server Installation ==="
echo "Install dir : $INSTALL_DIR"
echo "Listen      : $HOST:$PORT"

# Dependencies
apt-get update -qq
apt-get install -y python3 python3-pip python3-venv

# Create user
if ! id "$SERVICE_USER" &>/dev/null; then
  useradd --system --no-create-home --shell /bin/false "$SERVICE_USER"
fi

# Install files
mkdir -p "$INSTALL_DIR/server"
cp -r "$SCRIPT_DIR/server/"* "$INSTALL_DIR/server/"

# Copy pre-built frontend (if available)
if [ -d "$SCRIPT_DIR/frontend/dist" ]; then
  cp -r "$SCRIPT_DIR/frontend/dist" "$INSTALL_DIR/frontend/"
  echo "Frontend (pre-built) kopiert."
else
  echo "WARNUNG: Kein pre-built Frontend gefunden. Baue es erst mit:"
  echo "  cd frontend && npm install && npm run build"
fi

# Python venv
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/server/requirements.txt"

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# Systemd service
cat > /etc/systemd/system/patchpilot-server.service <<EOF
[Unit]
Description=PatchPilot Server
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/server
# PERFORMANCE: Tuned uvicorn flags for Raspberry Pi single-process deployment.
# --workers 1          : one process — no inter-process overhead, fits in RAM
# --limit-concurrency 20: cap concurrent requests; excess gets 503, not OOM
# --backlog 32         : small TCP accept queue — we're not a high-traffic host
# --log-level warning  : suppress access logs — fewer writes to SD card / journal
ExecStart=$INSTALL_DIR/venv/bin/uvicorn app:app \
    --host $HOST \
    --port $PORT \
    --workers 1 \
    --limit-concurrency 20 \
    --backlog 32 \
    --log-level warning
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable patchpilot-server
systemctl restart patchpilot-server

echo ""
echo "=== Installation abgeschlossen! ==="
echo "Status  : systemctl status patchpilot-server"
echo "Logs    : journalctl -u patchpilot-server -f"
echo "Web UI  : http://$(hostname -I | awk '{print $1}'):$PORT"
