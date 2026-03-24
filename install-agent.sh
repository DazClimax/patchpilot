#!/bin/bash
# PatchPilot — Agent Install Script
# Runs on each Debian VM that should be managed
# Usage: sudo bash install-agent.sh --server http://192.168.1.10:8000

set -e

SERVER=""
INTERVAL=60
INSTALL_DIR="/opt/patchpilot-agent"
CONFIG_DIR="/etc/patchpilot"
SERVICE_USER="root"  # needs root for apt-get
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --server) SERVER="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    *) echo "Unknown parameter: $1"; exit 1 ;;
  esac
done

if [ -z "$SERVER" ]; then
  echo "ERROR: --server is required"
  echo "Example: sudo bash install-agent.sh --server http://192.168.1.10:8000"
  exit 1
fi

echo "=== PatchPilot Agent Installation ==="
echo "Server   : $SERVER"
echo "Interval : ${INTERVAL}s"

# Dependencies (Python 3 stdlib only — no pip required)
apt-get update -qq
apt-get install -y python3

# Install
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/agent/agent.py" "$INSTALL_DIR/agent.py"
chmod +x "$INSTALL_DIR/agent.py"

# Config
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/agent.conf" ]; then
  cat > "$CONFIG_DIR/agent.conf" <<EOF
PATCHPILOT_SERVER=$SERVER
PATCHPILOT_INTERVAL=$INTERVAL
EOF
  echo "Config created: $CONFIG_DIR/agent.conf"
else
  # Update only server URL
  sed -i "s|PATCHPILOT_SERVER=.*|PATCHPILOT_SERVER=$SERVER|" "$CONFIG_DIR/agent.conf"
  echo "Config updated: $CONFIG_DIR/agent.conf"
fi

# Systemd
cat > /etc/systemd/system/patchpilot-agent.service <<EOF
[Unit]
Description=PatchPilot Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 $INSTALL_DIR/agent.py
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable patchpilot-agent
systemctl restart patchpilot-agent

echo ""
echo "=== Agent installed on $(hostname) ==="
echo "Status : systemctl status patchpilot-agent"
echo "Logs   : journalctl -u patchpilot-agent -f"
echo ""
echo "The agent will check in with the server within ${INTERVAL}s."
