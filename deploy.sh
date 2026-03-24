#!/bin/bash
# PatchPilot deploy script — never touches the production database
set -e

PI="${PATCHPILOT_HOST:?Set PATCHPILOT_HOST (e.g. root@your-server-ip)}"

echo "[deploy] Syncing server (excluding DB)..."
rsync -av --exclude='__pycache__' --exclude='*.pyc' --exclude='*.db' --exclude='*.db-shm' --exclude='*.db-wal' \
  server/ ${PI}:/opt/patchpilot/server/

echo "[deploy] Syncing frontend..."
rsync -av frontend/dist/ ${PI}:/opt/patchpilot/frontend/dist/

echo "[deploy] Syncing agent..."
rsync -av --exclude='__pycache__' --exclude='*.pyc' \
  agent/ ${PI}:/opt/patchpilot/agent/

echo "[deploy] Installing service file..."
scp patchpilot.service ${PI}:/etc/systemd/system/patchpilot.service
# Ensure required env vars are set (add defaults if missing)
ssh ${PI} "grep -q '^PORT=' /opt/patchpilot/.env || echo 'PORT=8443' >> /opt/patchpilot/.env"
ssh ${PI} "grep -q '^AGENT_PORT=' /opt/patchpilot/.env || echo 'AGENT_PORT=8050' >> /opt/patchpilot/.env"
ssh ${PI} "systemctl daemon-reload"

echo "[deploy] Ensuring patchpilot system user exists..."
ssh ${PI} "id patchpilot &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin patchpilot"
# Fix ownership after rsync (rsync preserves macOS UID 501 on the directory)
ssh ${PI} "chown patchpilot:patchpilot /opt/patchpilot/server/ && chown patchpilot:patchpilot /opt/patchpilot/server/patchpilot.db 2>/dev/null || true"
ssh ${PI} "chmod 600 /opt/patchpilot/.env 2>/dev/null || true"
# Ensure sudoers entry for service self-restart
ssh ${PI} "echo 'patchpilot ALL=(root) NOPASSWD: /bin/systemctl restart patchpilot' > /etc/sudoers.d/patchpilot && chmod 440 /etc/sudoers.d/patchpilot"

echo "[deploy] Enabling and restarting service..."
ssh ${PI} "systemctl enable patchpilot && systemctl restart patchpilot && sleep 2 && systemctl is-active patchpilot"

echo "[deploy] Done."
