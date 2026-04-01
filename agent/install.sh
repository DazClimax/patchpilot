#!/bin/bash
# PatchPilot Agent Installer
# Usage: sudo PATCHPILOT_SERVER=<url> PATCHPILOT_REGISTER_KEY=<key> bash install.sh
# For HTTPS with a self-signed certificate, provide PATCHPILOT_CA_PEM_B64.
# Set PATCHPILOT_INSECURE_BOOTSTRAP=1 only if you explicitly accept an
# unauthenticated first-cert bootstrap on a trusted network.
set -e

AGENT_ID="${PATCHPILOT_AGENT_ID:-$(hostname)}"
SERVER_URL="${PATCHPILOT_SERVER}"
REGISTER_KEY="${PATCHPILOT_REGISTER_KEY}"
CA_PEM_B64="${PATCHPILOT_CA_PEM_B64}"
CA_ROLLOVER_PUB_B64="${PATCHPILOT_CA_ROLLOVER_PUB_B64}"
INSECURE_BOOTSTRAP="${PATCHPILOT_INSECURE_BOOTSTRAP:-0}"
AGENT_DIR="/opt/patchpilot/agent"
CONFIG_DIR="/etc/patchpilot"
MISSING_PKGS=()

if [ -z "$SERVER_URL" ]; then
  echo "ERROR: PATCHPILOT_SERVER env var is required." >&2
  exit 1
fi

if [ -z "$REGISTER_KEY" ]; then
  echo "ERROR: PATCHPILOT_REGISTER_KEY env var is required." >&2
  echo "  Get the current key from the PatchPilot dashboard." >&2
  exit 1
fi

echo "[patchpilot] Starting installation..."

# ── Root check ────────────────────────────────────────────────────────────────
if [ "$(id -u)" != "0" ]; then
  echo "ERROR: Please run as root (sudo bash $0)" >&2
  exit 1
fi

# ── Detect package manager ────────────────────────────────────────────────────
if command -v apt-get &>/dev/null; then
  PKG_INSTALL="apt-get install -y -qq"
  PKG_UPDATE="apt-get update -qq"
elif command -v apt &>/dev/null; then
  PKG_INSTALL="apt install -y -qq"
  PKG_UPDATE="apt update -qq"
elif command -v dnf &>/dev/null; then
  PKG_INSTALL="dnf install -y -q"
  PKG_UPDATE="dnf makecache -q"
elif command -v yum &>/dev/null; then
  PKG_INSTALL="yum install -y -q"
  PKG_UPDATE="yum makecache -q"
else
  echo "ERROR: No supported package manager found (requires apt, dnf, or yum)" >&2
  exit 1
fi

# ── Check & collect missing packages ─────────────────────────────────────────
check_pkg() {
  local cmd="$1" pkg="$2"
  if ! command -v "$cmd" &>/dev/null; then
    echo "[patchpilot] Missing: $pkg"
    MISSING_PKGS+=("$pkg")
  fi
}

check_pkg python3   python3
check_pkg systemctl systemd
check_pkg openssl   openssl

# For downloading: need curl or wget
if ! command -v curl &>/dev/null && ! command -v wget &>/dev/null; then
  echo "[patchpilot] Missing: curl (no curl or wget found)"
  MISSING_PKGS+=("curl")
fi

# ── Install missing packages ──────────────────────────────────────────────────
if [ "${#MISSING_PKGS[@]}" -gt 0 ]; then
  echo "[patchpilot] Installing missing packages: ${MISSING_PKGS[*]}"
  $PKG_UPDATE
  $PKG_INSTALL "${MISSING_PKGS[@]}"
  echo "[patchpilot] Packages installed."
else
  echo "[patchpilot] All dependencies present."
fi

# ── Verify python3 is now available ──────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 could not be installed. Aborting." >&2
  exit 1
fi

# ── Create directories ────────────────────────────────────────────────────────
mkdir -p "$AGENT_DIR" "$CONFIG_DIR"

if [ -n "$CA_ROLLOVER_PUB_B64" ]; then
  printf '%s' "$CA_ROLLOVER_PUB_B64" | base64 -d > "$CONFIG_DIR/ca_rollover_public.pem"
  chmod 644 "$CONFIG_DIR/ca_rollover_public.pem"
fi

# ── SSL: fetch CA certificate if server uses HTTPS ───────────────────────────
CURL_OPTS=""
WGET_OPTS=""
if echo "$SERVER_URL" | grep -qi '^https://'; then
  if [ -n "$CA_PEM_B64" ]; then
    echo "[patchpilot] HTTPS server detected — installing embedded CA certificate..."
    printf '%s' "$CA_PEM_B64" | base64 -d > "$CONFIG_DIR/ca.pem"
    chmod 644 "$CONFIG_DIR/ca.pem"
    CURL_OPTS="--cacert $CONFIG_DIR/ca.pem"
    WGET_OPTS="--ca-certificate=$CONFIG_DIR/ca.pem"
  elif [ "$INSECURE_BOOTSTRAP" = "1" ]; then
    echo "[patchpilot] WARNING: using insecure HTTPS bootstrap because PATCHPILOT_INSECURE_BOOTSTRAP=1"
    if command -v curl &>/dev/null; then
      curl -fsSLk "$SERVER_URL/agent/ca.pem" -o "$CONFIG_DIR/ca.pem" 2>/dev/null || true
    else
      wget --no-check-certificate -qO "$CONFIG_DIR/ca.pem" "$SERVER_URL/agent/ca.pem" 2>/dev/null || true
    fi
    if [ -s "$CONFIG_DIR/ca.pem" ]; then
      echo "[patchpilot] CA certificate installed at $CONFIG_DIR/ca.pem"
      CURL_OPTS="--cacert $CONFIG_DIR/ca.pem"
      WGET_OPTS="--ca-certificate=$CONFIG_DIR/ca.pem"
    else
      echo "ERROR: Could not bootstrap CA certificate." >&2
      exit 1
    fi
  else
    echo "ERROR: HTTPS bootstrap requires PATCHPILOT_CA_PEM_B64." >&2
    echo "  Use the secure installer generated in the Deploy page, or set PATCHPILOT_INSECURE_BOOTSTRAP=1 to opt into insecure bootstrap." >&2
    exit 1
  fi
fi

# ── Download agent ────────────────────────────────────────────────────────────
echo "[patchpilot] Downloading agent from $SERVER_URL ..."
if command -v curl &>/dev/null; then
  curl -fsSL $CURL_OPTS "$SERVER_URL/agent/agent.py"        -o "$AGENT_DIR/agent.py"
  curl -fsSL $CURL_OPTS "$SERVER_URL/agent/agent.py.sha256" -o "$AGENT_DIR/agent.py.sha256"
else
  wget $WGET_OPTS -qO "$AGENT_DIR/agent.py"        "$SERVER_URL/agent/agent.py"
  wget $WGET_OPTS -qO "$AGENT_DIR/agent.py.sha256" "$SERVER_URL/agent/agent.py.sha256"
fi

if [ ! -s "$AGENT_DIR/agent.py" ]; then
  echo "ERROR: agent.py download failed or file is empty." >&2
  exit 1
fi

# ── Verify SHA256 integrity ───────────────────────────────────────────────────
if [ -s "$AGENT_DIR/agent.py.sha256" ] && command -v sha256sum &>/dev/null; then
  EXPECTED="$(cat "$AGENT_DIR/agent.py.sha256" | awk '{print $1}')"
  ACTUAL="$(sha256sum "$AGENT_DIR/agent.py" | awk '{print $1}')"
  if [ "$EXPECTED" != "$ACTUAL" ]; then
    echo "ERROR: agent.py SHA256 mismatch — download may be corrupted." >&2
    echo "  expected: $EXPECTED" >&2
    echo "  actual:   $ACTUAL" >&2
    exit 1
  fi
  echo "[patchpilot] SHA256 verified."
else
  echo "[patchpilot] WARNING: skipping integrity check (sha256 file or sha256sum not available)"
fi

chmod 755 "$AGENT_DIR/agent.py"
echo "[patchpilot] Agent downloaded."

# ── Write config ──────────────────────────────────────────────────────────────
CONFIG_CONTENT="PATCHPILOT_SERVER=${SERVER_URL}
PATCHPILOT_AGENT_ID=${AGENT_ID}
PATCHPILOT_REGISTER_KEY=${REGISTER_KEY}"

# Add CA bundle path if we downloaded it
if [ -s "$CONFIG_DIR/ca.pem" ]; then
  CONFIG_CONTENT="${CONFIG_CONTENT}
PATCHPILOT_CA_BUNDLE=${CONFIG_DIR}/ca.pem"
fi
if [ -s "$CONFIG_DIR/ca_rollover_public.pem" ]; then
  CONFIG_CONTENT="${CONFIG_CONTENT}
PATCHPILOT_CA_ROLLOVER_PUBKEY=${CONFIG_DIR}/ca_rollover_public.pem"
fi

echo "$CONFIG_CONTENT" > "$CONFIG_DIR/agent.conf"
chmod 600 "$CONFIG_DIR/agent.conf"

# ── Create systemd service ────────────────────────────────────────────────────
PYTHON3_BIN="$(command -v python3)"
cat > /etc/systemd/system/patchpilot-agent.service <<EOF
[Unit]
Description=PatchPilot Agent
After=network.target

[Service]
ExecStart=${PYTHON3_BIN} ${AGENT_DIR}/agent.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── Clear stale token so agent re-registers with fresh credentials ────────────
rm -f "$CONFIG_DIR/state.json"

systemctl daemon-reload
systemctl enable patchpilot-agent
systemctl restart patchpilot-agent

# ── Final status ──────────────────────────────────────────────────────────────
echo ""
echo "[patchpilot] ✓ Installation complete."
echo "[patchpilot]   Agent ID : ${AGENT_ID}"
echo "[patchpilot]   Server   : ${SERVER_URL}"
echo "[patchpilot]   Status   : $(systemctl is-active patchpilot-agent)"
echo "[patchpilot]   VM will appear in the dashboard within ~30 seconds."
