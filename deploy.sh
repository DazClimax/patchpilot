#!/bin/bash
# PatchPilot deploy script — never touches the production database
set -e

PI="${PATCHPILOT_HOST:?Set PATCHPILOT_HOST (e.g. root@your-server-ip)}"

validate_deploy_host() {
  case "$1" in
    -*)
      echo "[deploy] PATCHPILOT_HOST may not start with '-'." >&2
      exit 1
      ;;
  esac
  case "$1" in
    *[!A-Za-z0-9._:@\[\]-]*)
      echo "[deploy] PATCHPILOT_HOST contains unsupported characters." >&2
      exit 1
      ;;
  esac
}

validate_deploy_host "$PI"

echo "[deploy] Ensuring patchpilot system user exists..."
ssh -- "$PI" "id patchpilot &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin patchpilot"
ssh -- "$PI" "install -d -o patchpilot -g patchpilot /opt/patchpilot /opt/patchpilot/server /opt/patchpilot/frontend/dist /opt/patchpilot/agent /opt/patchpilot/home-assistant-addons"

echo "[deploy] Syncing server (excluding DB)..."
rsync -av --exclude='__pycache__' --exclude='*.pyc' --exclude='*.db' --exclude='*.db-shm' --exclude='*.db-wal' \
  -- server/ "${PI}:/opt/patchpilot/server/"

echo "[deploy] Syncing frontend..."
rsync -av -- frontend/dist/ "${PI}:/opt/patchpilot/frontend/dist/"

echo "[deploy] Syncing agent..."
rsync -av --exclude='__pycache__' --exclude='*.pyc' \
  -- agent/ "${PI}:/opt/patchpilot/agent/"

echo "[deploy] Syncing Home Assistant add-on files..."
rsync -av --exclude='__pycache__' --exclude='*.pyc' \
  -- home-assistant-addons/ "${PI}:/opt/patchpilot/home-assistant-addons/"

echo "[deploy] Installing pip requirements..."
ssh -- "$PI" "/opt/patchpilot-venv/bin/pip install --quiet -r /opt/patchpilot/server/requirements.txt"

echo "[deploy] Installing service file..."
scp -- patchpilot.service "${PI}:/etc/systemd/system/patchpilot.service"
scp -- patchpilot.logrotate "${PI}:/etc/logrotate.d/patchpilot"
# Ensure required env vars are set (add defaults if missing)
ssh -- "$PI" "grep -q '^PORT=' /opt/patchpilot/.env || echo 'PORT=8443' >> /opt/patchpilot/.env"
ssh -- "$PI" "grep -q '^AGENT_PORT=' /opt/patchpilot/.env || echo 'AGENT_PORT=8050' >> /opt/patchpilot/.env"
ssh -- "$PI" "systemctl daemon-reload"

ssh -- "$PI" "chown -R patchpilot:patchpilot /opt/patchpilot/server /opt/patchpilot/frontend /opt/patchpilot/agent /opt/patchpilot/home-assistant-addons"
ssh -- "$PI" "touch /opt/patchpilot/.env && chown patchpilot:patchpilot /opt/patchpilot/.env"
ssh -- "$PI" "chmod 755 /opt/patchpilot /opt/patchpilot/server /opt/patchpilot/frontend /opt/patchpilot/frontend/dist /opt/patchpilot/agent /opt/patchpilot/home-assistant-addons 2>/dev/null || true"
ssh -- "$PI" "find /opt/patchpilot/server -maxdepth 1 -type f -name 'patchpilot.db*' -exec chown patchpilot:patchpilot {} + -exec chmod 600 {} + 2>/dev/null || true"
ssh -- "$PI" "find /opt/patchpilot -maxdepth 1 -type f -name 'patchpilot.db*' -size 0 -delete 2>/dev/null || true"
ssh -- "$PI" "chmod 600 /opt/patchpilot/.env 2>/dev/null || true"
ssh -- "$PI" "install -d -o patchpilot -g patchpilot -m 0750 /var/log/patchpilot && touch /var/log/patchpilot/server.log && chown patchpilot:patchpilot /var/log/patchpilot/server.log && chmod 640 /var/log/patchpilot/server.log"
# Ensure sudoers entry for service self-restart
ssh -- "$PI" "echo 'patchpilot ALL=(root) NOPASSWD: /bin/systemctl restart patchpilot' > /etc/sudoers.d/patchpilot && chmod 440 /etc/sudoers.d/patchpilot"

echo "[deploy] Enabling and restarting service..."
ssh -- "$PI" "systemctl enable patchpilot && systemctl restart patchpilot && sleep 2 && systemctl is-active patchpilot"

echo "[deploy] Done."
