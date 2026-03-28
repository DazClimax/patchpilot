#!/bin/bash
# PatchPilot — One-liner server setup
# Usage: curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/v1.6.0/setup.sh | sudo bash
#
# Or with custom ports:
#   curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/v1.6.0/setup.sh | sudo PORT=443 AGENT_PORT=8050 bash

set -e

REPO="https://github.com/DazClimax/patchpilot.git"
INSTALL_TMP="/tmp/patchpilot-install"
PATCHPILOT_REF="${PATCHPILOT_REF:-v1.6.0}"

echo "=== PatchPilot Setup ==="
echo ""

# ── 1. Install system dependencies ──────────────────────────────────────────
echo "[1/5] Installing dependencies..."
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
echo "[2/5] Cloning PatchPilot ${PATCHPILOT_REF}..."
rm -rf "$INSTALL_TMP"
git clone --depth 1 --branch "$PATCHPILOT_REF" "$REPO" "$INSTALL_TMP"
cd "$INSTALL_TMP"

# ── 3. Build frontend ──────────────────────────────────────────────────────
echo "[3/5] Building frontend..."
cd frontend
npm install --no-audit --no-fund --loglevel=error
npm run build
cd ..

# ── 4. Run installer ───────────────────────────────────────────────────────
echo "[4/5] Running server installer..."
bash install-server.sh

# ── 5. Cleanup ──────────────────────────────────────────────────────────────
echo "[5/5] Cleaning up..."
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
echo "  Default login: admin / (check logs)"
echo "  journalctl -u patchpilot | grep password"
echo ""
