#!/bin/bash
# PatchPilot — One-liner server setup
# Usage: curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/v1.6.3/setup.sh | sudo bash
#
# Or with custom ports:
#   curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/v1.6.3/setup.sh | sudo PORT=443 AGENT_PORT=8050 bash

set -e

REPO="https://github.com/DazClimax/patchpilot.git"
INSTALL_TMP="/tmp/patchpilot-install"
PATCHPILOT_REF="${PATCHPILOT_REF:-v1.6.3}"
LOG_FILE="/var/log/patchpilot-setup.log"

require_root() {
  if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    echo "[patchpilot] Please run this installer as root." >&2
    echo "[patchpilot] Example: curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/${PATCHPILOT_REF}/setup.sh | sudo bash" >&2
    exit 1
  fi
}

require_apt() {
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "[patchpilot] This server bootstrap currently supports Debian/Ubuntu-style hosts with apt." >&2
    echo "[patchpilot] RPM support currently applies to managed clients/agents, not to the PatchPilot server installer." >&2
    exit 1
  fi
}

log_setup() {
  mkdir -p "$(dirname "$LOG_FILE")"
  touch "$LOG_FILE"
  chmod 600 "$LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
}

step() {
  echo ""
  echo "[$1/5] $2"
}

require_root
require_apt
log_setup

echo "=== PatchPilot Setup ==="
echo ""
echo "Log file   : $LOG_FILE"
echo "Release    : $PATCHPILOT_REF"
echo "Host type  : Debian/Ubuntu-style server bootstrap"
echo ""

# ── 1. Install system dependencies ──────────────────────────────────────────
step 1 "Installing dependencies"
apt-get update -qq
apt-get install -y git curl python3 python3-pip python3-venv openssl ca-certificates gnupg

# Node.js (via NodeSource if not installed or too old)
if ! command -v node &>/dev/null || [ "$(node -v | cut -d. -f1 | tr -d v)" -lt 18 ]; then
  echo "[1/5] Installing Node.js 20..."
  mkdir -p /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg 2>/dev/null
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list
  apt-get update -qq
  apt-get install -y nodejs
else
  echo "[1/5] Node.js $(node -v) found — OK"
fi

# ── 2. Clone repository ────────────────────────────────────────────────────
step 2 "Cloning PatchPilot ${PATCHPILOT_REF}"
rm -rf "$INSTALL_TMP"
git clone --depth 1 --branch "$PATCHPILOT_REF" "$REPO" "$INSTALL_TMP"
cd "$INSTALL_TMP"

# ── 3. Build frontend ──────────────────────────────────────────────────────
step 3 "Building frontend"
cd frontend
npm install --no-audit --no-fund --loglevel=error
npm run build
cd ..

# ── 4. Run installer ───────────────────────────────────────────────────────
step 4 "Running server installer"
bash install-server.sh

# ── 5. Cleanup ──────────────────────────────────────────────────────────────
step 5 "Cleaning up"
rm -rf "$INSTALL_TMP"

IP="$(hostname -I | awk '{print $1}')"
PORT="${PORT:-8443}"
echo ""
echo "========================================="
echo "  PatchPilot installed successfully!"
echo "========================================="
echo ""
echo "  Web UI  : https://${IP}:${PORT}"
echo "  Status  : systemctl status patchpilot"
echo "  Logs    : journalctl -u patchpilot -f"
echo ""
echo "  Default login: admin / (see bootstrap file)"
echo "  Admin pass : sudo cat /opt/patchpilot/bootstrap-admin.txt"
echo "  Installer log: $LOG_FILE"
echo ""
