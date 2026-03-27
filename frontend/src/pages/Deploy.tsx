import { useState, useEffect, useRef, useCallback } from 'react'
import { colors, glow, glowText, glowStrong, glassBg } from '../theme'
import { PageHeader, SectionHeader } from '../components/SectionHeader'
import { Card } from '../components/Card'
import { Button } from '../components/Button'
import { api } from '../api/client'

const REGISTER_KEY_STORAGE_KEY = 'pp_deploy_register_key'
const REGISTER_KEY_EXPIRY_STORAGE_KEY = 'pp_deploy_register_key_expires_at'

function persistRegisterKeyState(key: string, expiresIn: number) {
  if (typeof window === 'undefined') return
  if (!key || expiresIn <= 0) {
    window.sessionStorage.removeItem(REGISTER_KEY_STORAGE_KEY)
    window.sessionStorage.removeItem(REGISTER_KEY_EXPIRY_STORAGE_KEY)
    return
  }
  window.sessionStorage.setItem(REGISTER_KEY_STORAGE_KEY, key)
  window.sessionStorage.setItem(REGISTER_KEY_EXPIRY_STORAGE_KEY, String(Date.now() + expiresIn * 1000))
}

function clearRegisterKeyState() {
  persistRegisterKeyState('', 0)
}

function readRegisterKeyState(): { key: string; expiresIn: number } {
  if (typeof window === 'undefined') return { key: '', expiresIn: 0 }
  const key = window.sessionStorage.getItem(REGISTER_KEY_STORAGE_KEY) ?? ''
  const expiresAtRaw = window.sessionStorage.getItem(REGISTER_KEY_EXPIRY_STORAGE_KEY)
  const expiresAt = expiresAtRaw ? Number(expiresAtRaw) : 0
  const expiresIn = expiresAt ? Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000)) : 0
  if (!key || expiresIn <= 0) {
    clearRegisterKeyState()
    return { key: '', expiresIn: 0 }
  }
  return { key, expiresIn }
}

function copyToClipboard(text: string): boolean {
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).catch(() => {})
    return true
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0'
  document.body.appendChild(ta)
  ta.focus()
  ta.select()
  const ok = document.execCommand('copy')
  document.body.removeChild(ta)
  return ok
}

function CopyButton({ text, label = 'Copy', disabled = false }: { text: string; label?: string; disabled?: boolean }) {
  const [copied, setCopied] = useState(false)

  const copy = () => {
    if (disabled || !text) return
    copyToClipboard(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const c = disabled ? colors.textMuted : copied ? colors.success : colors.primary
  return (
    <button
      onClick={copy}
      disabled={disabled}
      style={{
        background: `${c}12`,
        border: `1px solid ${c}66`,
        color: c,
        cursor: disabled ? 'not-allowed' : 'pointer',
        padding: '6px 16px',
        fontSize: '11px',
        fontFamily: "'Electrolize', monospace",
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        textShadow: glowText(c, 3),
        transition: 'all 0.2s',
        clipPath: 'polygon(4px 0%, 100% 0%, calc(100% - 4px) 100%, 0% 100%)',
        whiteSpace: 'nowrap',
        opacity: disabled ? 0.45 : 1,
      }}
    >
      {copied ? '✓ Copied' : label}
    </button>
  )
}

// ─── Register Key Widget ──────────────────────────────────────────────────────

function RegisterKeyWidget({ registerKey, setRegisterKey, expiresIn, setExpiresIn }: {
  registerKey: string;
  setRegisterKey: (k: string) => void;
  expiresIn: number;
  setExpiresIn: React.Dispatch<React.SetStateAction<number>>;
}) {
  const [generating, setGenerating] = useState(false)
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!registerKey || expiresIn <= 0) return
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = setInterval(() => {
      const state = readRegisterKeyState()
      setExpiresIn(state.expiresIn)
      if (state.expiresIn <= 0) {
        setRegisterKey('')
        clearRegisterKeyState()
        if (timerRef.current) {
          setRegisterKey('')
          clearInterval(timerRef.current)
          timerRef.current = null
        }
      }
    }, 1000)
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [registerKey, expiresIn, setRegisterKey, setExpiresIn])

  const generate = async () => {
    setGenerating(true)
    try {
      const r = await api.generateRegisterKey()
      setRegisterKey(r.key)
      setExpiresIn(r.expires_in)
      persistRegisterKeyState(r.key, r.expires_in)
    } catch (e) {
      console.error(e)
    } finally {
      setGenerating(false)
    }
  }

  const key = registerKey
  const keyUsable = !!key && expiresIn > 0

  const copyKey = () => {
    if (keyUsable) {
      copyToClipboard(key)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
  const pct = keyUsable ? (expiresIn / 300) * 100 : 0

  return (
    <Card style={{ padding: '18px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
        <div style={{
          fontSize: '11px', color: colors.textMuted,
          fontFamily: "'Orbitron', sans-serif",
          letterSpacing: '0.18em', textTransform: 'uppercase',
          flexShrink: 0,
        }}>
          Registration Key
        </div>

        {keyUsable ? (
          <>
            <code
              onClick={copyKey}
              title="Click to copy"
              style={{
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                fontSize: '16px',
                color: colors.primary,
                letterSpacing: '0.2em',
                cursor: 'pointer',
                userSelect: 'all',
                textShadow: glowText(colors.primary, 4),
                padding: '4px 12px',
                border: `1px solid ${colors.primary}33`,
                background: `${colors.primary}08`,
              }}
            >
              {key}
            </code>
            {copied && <span style={{ fontSize: '10px', color: colors.success }}>copied</span>}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{
                width: '80px', height: '4px',
                background: `${colors.border}`,
                overflow: 'hidden',
              }}>
                <div style={{
                  width: `${pct}%`, height: '100%',
                  background: expiresIn < 60 ? colors.danger : colors.primary,
                  boxShadow: `0 0 6px ${expiresIn < 60 ? colors.danger : colors.primary}66`,
                  transition: 'width 1s linear, background 0.3s',
                }} />
              </div>
              <span style={{
                fontSize: '11px',
                color: expiresIn < 60 ? colors.danger : colors.textMuted,
                fontVariantNumeric: 'tabular-nums',
                fontFamily: 'monospace',
              }}>
                {fmtTime(expiresIn)}
              </span>
            </div>
            <Button variant="ghost" size="sm" onClick={generate} disabled={generating}>
              ↻ New Key
            </Button>
          </>
        ) : (
          <>
            <span style={{ fontSize: '12px', color: expiresIn > 0 ? colors.warn : colors.textMuted, fontFamily: 'monospace' }}>
              {expiresIn > 0
                ? `Active key expires in ${Math.floor(expiresIn / 60)}:${String(expiresIn % 60).padStart(2, '0')} — generate new to reveal`
                : 'No active key — generate one to register new agents'}
            </span>
            <Button variant="primary" size="sm" onClick={generate} disabled={generating}>
              {generating ? '⟳ Generating…' : '🔑 Generate Key'}
            </Button>
          </>
        )}
      </div>
      <div style={{
        fontSize: '10px', color: colors.textMuted, marginTop: '8px',
        fontFamily: 'monospace', letterSpacing: '0.04em',
      }}>
        Key is valid for 5 minutes. A new key replaces the previous one. Without an active key, no new agents can register.
      </div>
    </Card>
  )
}

// ─── Deploy Page ──────────────────────────────────────────────────────────────

const AGENT_ID_RE = /^[a-zA-Z0-9._-]{1,64}$/
const SERVER_URL_RE = /^https?:\/\/[a-zA-Z0-9._:[\]-]+$/

function shellSingleQuote(value: string): string {
  return `'${value.replace(/'/g, `'\"'\"'`)}'`
}

function decodePemFromBase64(value: string): string {
  if (!value) return ''
  try {
    return atob(value)
  } catch {
    return ''
  }
}

function buildHaAddonConfig(serverUrl: string, agentId: string, registerKey: string, caPemB64: string): string {
  const lines = [
    `patchpilot_server: ${JSON.stringify(serverUrl)}`,
    `register_key: ${JSON.stringify(registerKey || '<REGISTER_KEY>')}`,
    `agent_id: ${JSON.stringify(agentId || 'homeassistant')}`,
    'poll_interval: 30',
  ]
  const pem = decodePemFromBase64(caPemB64).trim()
  if (pem) {
    lines.push('ca_pem: |')
    for (const line of pem.split('\n')) {
      lines.push(`  ${line}`)
    }
  } else {
    lines.push('ca_pem: ""')
  }
  return lines.join('\n')
}

function buildOneLiner(serverUrl: string, agentId: string, registerKey: string, caPemB64: string): string {
  const effectiveRegisterKey = registerKey || '<KEY>'
  const envParts = [
    `PATCHPILOT_SERVER=${shellSingleQuote(serverUrl)}`,
    `PATCHPILOT_REGISTER_KEY=${shellSingleQuote(effectiveRegisterKey)}`,
  ]
  if (agentId) {
    envParts.push(`PATCHPILOT_AGENT_ID=${shellSingleQuote(agentId)}`)
  }

  if (serverUrl.toLowerCase().startsWith('https://')) {
    const ca = shellSingleQuote(caPemB64)
    const installUrl = shellSingleQuote(`${serverUrl}/agent/install.sh`)
    return [
      `PP_CA_B64=${ca}`,
      'PP_CA_FILE=$(mktemp)',
      `printf '%s' "$PP_CA_B64" | base64 -d > "$PP_CA_FILE"`,
      `curl -fsSL --cacert "$PP_CA_FILE" ${installUrl} | sudo ${envParts.join(' ')} PATCHPILOT_CA_PEM_B64="$PP_CA_B64" bash`,
      'rm -f "$PP_CA_FILE"',
    ].join(' && ')
  }

  const installUrl = shellSingleQuote(`${serverUrl}/agent/install.sh`)
  return `curl -fsSL ${installUrl} | sudo ${envParts.join(' ')} bash`
}

function buildScript(serverUrl: string, agentId: string, registerKey: string, caPemB64: string): string {
  // Build as array to avoid template-literal escaping nightmare with shell ${}
  const D = '$'  // shell dollar sign
  const effectiveRegisterKey = registerKey || '<KEY>'
  const caLine = caPemB64 ? `CA_PEM_B64=${shellSingleQuote(caPemB64)}` : "CA_PEM_B64=''"
  const lines = [
    '#!/bin/bash',
    '# PatchPilot Agent Installer',
    `# Server: ${serverUrl}`,
    'set -e',
    '',
    `AGENT_ID="${D}{PATCHPILOT_AGENT_ID:-${agentId || `${D}(hostname)`}}"`,
    `SERVER_URL="${serverUrl}"`,
    `REGISTER_KEY="${effectiveRegisterKey}"`,
    caLine,
    'AGENT_DIR="/opt/patchpilot/agent"',
    'CONFIG_DIR="/etc/patchpilot"',
    'MISSING_PKGS=()',
    '',
    'echo "[patchpilot] Starting installation..."',
    '',
    '# ── Root check ────────────────────────────────────────────────────────────────',
    `if [ "${D}(id -u)" != "0" ]; then`,
    `  echo "ERROR: Please run as root (sudo bash ${D}0)" >&2`,
    '  exit 1',
    'fi',
    '',
    '# ── Detect package manager ────────────────────────────────────────────────────',
    'if command -v apt-get &>/dev/null; then',
    '  PKG_INSTALL="apt-get install -y -qq"',
    '  PKG_UPDATE="apt-get update -qq"',
    'elif command -v apt &>/dev/null; then',
    '  PKG_INSTALL="apt install -y -qq"',
    '  PKG_UPDATE="apt update -qq"',
    'elif command -v dnf &>/dev/null; then',
    '  PKG_INSTALL="dnf install -y -q"',
    '  PKG_UPDATE="dnf makecache -q"',
    'elif command -v yum &>/dev/null; then',
    '  PKG_INSTALL="yum install -y -q"',
    '  PKG_UPDATE="yum makecache -q"',
    'else',
    '  echo "ERROR: No supported package manager found (requires apt, dnf, or yum)" >&2',
    '  exit 1',
    'fi',
    '',
    '# ── Check & collect missing packages ─────────────────────────────────────────',
    'check_pkg() {',
    `  local cmd="${D}1" pkg="${D}2"`,
    `  if ! command -v "${D}cmd" &>/dev/null; then`,
    `    echo "[patchpilot] Missing: ${D}pkg"`,
    `    MISSING_PKGS+=("${D}pkg")`,
    '  fi',
    '}',
    '',
    'check_pkg python3   python3',
    'check_pkg systemctl systemd',
    '',
    'if ! command -v curl &>/dev/null && ! command -v wget &>/dev/null; then',
    '  echo "[patchpilot] Missing: curl (no curl or wget found)"',
    '  MISSING_PKGS+=("curl")',
    'fi',
    '',
    '# ── Install missing packages ──────────────────────────────────────────────────',
    `if [ "${D}{#MISSING_PKGS[@]}" -gt 0 ]; then`,
    `  echo "[patchpilot] Installing missing packages: ${D}{MISSING_PKGS[*]}"`,
    `  ${D}PKG_UPDATE`,
    `  ${D}PKG_INSTALL "${D}{MISSING_PKGS[@]}"`,
    '  echo "[patchpilot] Packages installed."',
    'else',
    '  echo "[patchpilot] All dependencies present."',
    'fi',
    '',
    'if ! command -v python3 &>/dev/null; then',
    '  echo "ERROR: python3 could not be installed. Aborting." >&2',
    '  exit 1',
    'fi',
    '',
    '# ── Create directories ────────────────────────────────────────────────────────',
    `mkdir -p "${D}AGENT_DIR" "${D}CONFIG_DIR"`,
    '',
    '# ── SSL bootstrap ────────────────────────────────────────────────────────────',
    'CURL_OPTS=""',
    'WGET_OPTS=""',
    `if echo "${D}SERVER_URL" | grep -qi '^https://'; then`,
    `  if [ -z "${D}CA_PEM_B64" ]; then`,
    '    echo "ERROR: HTTPS bootstrap data missing. Regenerate this installer from the Deploy page." >&2',
    '    exit 1',
    '  fi',
    `  printf '%s' "${D}CA_PEM_B64" | base64 -d > "${D}CONFIG_DIR/ca.pem"`,
    `  chmod 644 "${D}CONFIG_DIR/ca.pem"`,
    `  CURL_OPTS="--cacert ${D}CONFIG_DIR/ca.pem"`,
    `  WGET_OPTS="--ca-certificate=${D}CONFIG_DIR/ca.pem"`,
    'fi',
    '',
    '# ── Download agent ────────────────────────────────────────────────────────────',
    `echo "[patchpilot] Downloading agent from ${D}SERVER_URL ..."`,
    'if command -v curl &>/dev/null; then',
    `  curl -fsSL ${D}CURL_OPTS "${D}SERVER_URL/agent/agent.py"        -o "${D}AGENT_DIR/agent.py"`,
    `  curl -fsSL ${D}CURL_OPTS "${D}SERVER_URL/agent/agent.py.sha256" -o "${D}AGENT_DIR/agent.py.sha256"`,
    'else',
    `  wget ${D}WGET_OPTS -qO "${D}AGENT_DIR/agent.py"        "${D}SERVER_URL/agent/agent.py"`,
    `  wget ${D}WGET_OPTS -qO "${D}AGENT_DIR/agent.py.sha256" "${D}SERVER_URL/agent/agent.py.sha256"`,
    'fi',
    '',
    `if [ ! -s "${D}AGENT_DIR/agent.py" ]; then`,
    '  echo "ERROR: agent.py download failed or file is empty." >&2',
    '  exit 1',
    'fi',
    '',
    '# ── Verify SHA256 integrity ───────────────────────────────────────────────────',
    `if [ -s "${D}AGENT_DIR/agent.py.sha256" ] && command -v sha256sum &>/dev/null; then`,
    `  EXPECTED="${D}(cat "${D}AGENT_DIR/agent.py.sha256" | awk '{print ${D}1}')"`,
    `  ACTUAL="${D}(sha256sum "${D}AGENT_DIR/agent.py" | awk '{print ${D}1}')"`,
    `  if [ "${D}EXPECTED" != "${D}ACTUAL" ]; then`,
    '    echo "ERROR: agent.py SHA256 mismatch — download may be corrupted." >&2',
    '    exit 1',
    '  fi',
    '  echo "[patchpilot] SHA256 verified."',
    'fi',
    '',
    `chmod 755 "${D}AGENT_DIR/agent.py"`,
    'echo "[patchpilot] Agent downloaded."',
    '',
    '# ── Write config ──────────────────────────────────────────────────────────────',
    `cat > "${D}CONFIG_DIR/agent.conf" <<CONF`,
    `PATCHPILOT_SERVER=${D}{SERVER_URL}`,
    `PATCHPILOT_AGENT_ID=${D}{AGENT_ID}`,
    `PATCHPILOT_REGISTER_KEY=${D}{REGISTER_KEY}`,
    'CONF',
    '# Add CA bundle path if we downloaded it',
    `if [ -s "${D}CONFIG_DIR/ca.pem" ]; then`,
    `  echo "PATCHPILOT_CA_BUNDLE=${D}CONFIG_DIR/ca.pem" >> "${D}CONFIG_DIR/agent.conf"`,
    'fi',
    `chmod 600 "${D}CONFIG_DIR/agent.conf"`,
    '',
    '# ── Create systemd service ────────────────────────────────────────────────────',
    `PYTHON3_BIN="${D}(command -v python3)"`,
    'cat > /etc/systemd/system/patchpilot-agent.service <<SVC',
    '[Unit]',
    'Description=PatchPilot Agent',
    'After=network.target',
    '',
    '[Service]',
    `ExecStart=${D}{PYTHON3_BIN} ${D}{AGENT_DIR}/agent.py`,
    'Restart=always',
    'RestartSec=30',
    'StandardOutput=journal',
    'StandardError=journal',
    '',
    '[Install]',
    'WantedBy=multi-user.target',
    'SVC',
    '',
    '# ── Clear stale token so agent re-registers ──────────────────────────────────',
    `rm -f "${D}CONFIG_DIR/state.json"`,
    '',
    'systemctl daemon-reload',
    'systemctl enable patchpilot-agent',
    'systemctl restart patchpilot-agent',
    '',
    '# ── Final status ──────────────────────────────────────────────────────────────',
    'echo ""',
    'echo "[patchpilot] Installation complete."',
    `echo "[patchpilot]   Agent ID : ${D}{AGENT_ID}"`,
    `echo "[patchpilot]   Server   : ${D}{SERVER_URL}"`,
    `echo "[patchpilot]   Status   : ${D}(systemctl is-active patchpilot-agent)"`,
    'echo "[patchpilot]   VM will appear in the dashboard within ~30 seconds."',
  ]
  return lines.join('\n')
}

export function DeployPage() {
  const [internalUrl, setInternalUrl] = useState('')
  const [pageReady, setPageReady] = useState(false)
  const [serverUrl, setServerUrl] = useState('')
  const [agentId, setAgentId] = useState('')
  const [registerKey, setRegisterKey] = useState('')
  const [expiresIn, setExpiresIn] = useState(0)
  const [caPemB64, setCaPemB64] = useState('')

  // Load settings + active key in parallel on mount
  useEffect(() => {
    const cached = readRegisterKeyState()
    if (cached.key && cached.expiresIn > 0) {
      setRegisterKey(cached.key)
      setExpiresIn(cached.expiresIn)
    }
    Promise.all([
      api.settings().then((s: any) => {
        // Prefer agent_url (HTTP, agent port) over internal_url (UI port, may be HTTPS)
        if (s.agent_url) setInternalUrl(s.agent_url)
        else if (s.internal_url) setInternalUrl(s.internal_url)
      }).catch(() => {}),
      api.registerKeyStatus().then(r => {
        const state = readRegisterKeyState()
        if (r.active && state.key && state.expiresIn > 0) {
          setRegisterKey(state.key)
          setExpiresIn(state.expiresIn)
        } else if (r.active && r.key) {
          setRegisterKey(r.key)
          setExpiresIn(r.expires_in)
          persistRegisterKeyState(r.key, r.expires_in)
        } else if (r.active) {
          // Server still has an active key, but plaintext is unavailable after reload
          // unless this browser cached it locally.
          setRegisterKey(state.key)
          setExpiresIn(state.expiresIn)
          if (!state.key) clearRegisterKeyState()
        } else {
          setRegisterKey('')
          setExpiresIn(0)
          clearRegisterKeyState()
        }
      }).catch(() => {}),
      api.deployBootstrap().then(r => {
        setCaPemB64(r.ca_pem_b64 || '')
      }).catch(() => {}),
    ]).finally(() => setPageReady(true))
  }, [])

  useEffect(() => {
    if (!registerKey || expiresIn <= 0) {
      clearRegisterKeyState()
      return
    }
    persistRegisterKeyState(registerKey, expiresIn)
  }, [registerKey, expiresIn])

  // Default: server-detected internal IP:port. User can override.
  const effectiveUrl = serverUrl || internalUrl

  const keyUsable = !!registerKey && expiresIn > 0

  const agentIdError = agentId.length > 0 && !AGENT_ID_RE.test(agentId)
    ? 'Only letters, numbers, dots, hyphens and underscores allowed (max 64)'
    : null
  const safeAgentId = AGENT_ID_RE.test(agentId) ? agentId : ''

  const urlValid = SERVER_URL_RE.test(effectiveUrl)
  const script = urlValid && keyUsable
    ? buildScript(effectiveUrl, safeAgentId, registerKey, caPemB64)
    : ''
  const oneliner = urlValid && keyUsable ? buildOneLiner(effectiveUrl, safeAgentId, registerKey, caPemB64) : ''
  const haAddonConfig = urlValid && keyUsable ? buildHaAddonConfig(effectiveUrl, safeAgentId, registerKey, caPemB64) : ''
  const haRepoUrl = 'https://github.com/DazClimax/patchpilot'

  const downloadScript = () => {
    if (!script) return
    const blob = new Blob([script], { type: 'text/x-shellscript' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'install-patchpilot-agent.sh'
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 200)
  }

  return (
    <div style={{ padding: 'clamp(16px, 4vw, 32px)', maxWidth: '1400px', animation: 'pp-fadein 0.4s ease both' }}>
      <PageHeader>Deploy Agent</PageHeader>

      {!pageReady ? (
        <div style={{ color: colors.textMuted, fontSize: '12px', fontFamily: "'Electrolize', monospace", padding: '20px 0' }}>
          Loading configuration...
        </div>
      ) : <>

      {/* Step 1 — Registration Key */}
      <div style={{ marginBottom: '28px' }}>
        <SectionHeader>1. Generate Registration Key</SectionHeader>
        <RegisterKeyWidget registerKey={registerKey} setRegisterKey={setRegisterKey} expiresIn={expiresIn} setExpiresIn={setExpiresIn} />
      </div>

      {/* Step 2 — Configure */}
      <div style={{ marginBottom: '28px' }}>
        <SectionHeader>2. Configure</SectionHeader>
        <Card style={{ padding: '20px 22px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap', marginBottom: '12px' }}>
            <div style={{
              fontSize: '11px', color: colors.textMuted,
              fontFamily: "'Orbitron', sans-serif",
              letterSpacing: '0.18em', textTransform: 'uppercase',
              flexShrink: 0, minWidth: '100px',
            }}>
              Server URL
            </div>
            <input
              value={serverUrl}
              onChange={e => setServerUrl(e.target.value)}
              placeholder={internalUrl || 'http://192.168.x.x:8050'}
              style={{
                flex: 1,
                minWidth: 'min(260px, 100%)',
                background: `${colors.bg}cc`,
                border: `1px solid ${colors.border}`,
                color: colors.text,
                padding: '8px 14px',
                fontSize: '13px',
                fontFamily: 'monospace',
                outline: 'none',
                transition: 'border-color 0.15s, box-shadow 0.15s',
              }}
              onFocus={e => {
                e.currentTarget.style.borderColor = colors.primary
                e.currentTarget.style.boxShadow = `0 0 0 1px ${colors.primary}44, inset 0 0 12px ${colors.primary}08`
              }}
              onBlur={e => {
                e.currentTarget.style.borderColor = colors.border
                e.currentTarget.style.boxShadow = 'none'
              }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
            <div style={{
              fontSize: '11px', color: colors.textMuted,
              fontFamily: "'Orbitron', sans-serif",
              letterSpacing: '0.18em', textTransform: 'uppercase',
              flexShrink: 0, minWidth: '100px',
            }}>
              VM Name / ID
            </div>
            <input
              value={agentId}
              onChange={e => setAgentId(e.target.value.replace(/\s+/g, '-'))}
              placeholder="optional — defaults to hostname"
              maxLength={64}
              style={{
                flex: 1,
                minWidth: 'min(260px, 100%)',
                background: `${colors.bg}cc`,
                border: `1px solid ${colors.border}`,
                color: colors.text,
                padding: '8px 14px',
                fontSize: '13px',
                fontFamily: 'monospace',
                outline: 'none',
                transition: 'border-color 0.15s, box-shadow 0.15s',
              }}
              onFocus={e => {
                e.currentTarget.style.borderColor = colors.primary
                e.currentTarget.style.boxShadow = `0 0 0 1px ${colors.primary}44, inset 0 0 12px ${colors.primary}08`
              }}
              onBlur={e => {
                e.currentTarget.style.borderColor = colors.border
                e.currentTarget.style.boxShadow = 'none'
              }}
            />
          </div>
          {agentIdError && (
            <div style={{ marginTop: '8px', fontSize: '11px', color: colors.danger, fontFamily: 'monospace' }}>
              ✕ {agentIdError}
            </div>
          )}
          <div style={{ marginTop: '8px', fontSize: '10px', color: colors.textMuted, fontFamily: 'monospace' }}>
            The server URL is what agents use to connect. If you access PatchPilot through a reverse proxy,
            enter the <strong>internal</strong> IP:port here (e.g. http://192.168.1.20:8050).
          </div>
        </Card>
      </div>

      {/* Step 3 — One-liner */}
      <div style={{ marginBottom: '28px' }}>
        <SectionHeader right={urlValid && keyUsable ? <CopyButton text={oneliner} label="Copy Command" /> : undefined}>
          3. Quick Install (One-Liner)
        </SectionHeader>
        {oneliner ? (
          <>
            <div style={{
              background: 'rgba(1,8,10,0.95)',
              border: `1px solid ${colors.border}`,
              padding: '16px 20px',
              fontFamily: "'Courier New', Courier, monospace",
              fontSize: '12px',
              color: colors.success,
              textShadow: glow(colors.success, 2),
              overflowX: 'auto',
              overflowY: 'hidden',
              whiteSpace: 'pre',
              wordBreak: 'normal',
              lineHeight: 1.5,
              position: 'relative',
            }}>
              <div style={{
                position: 'absolute', top: 0, left: 0, right: 0, height: '1px',
                background: `linear-gradient(90deg, transparent, ${colors.primary}55, transparent)`,
              }} />
              {oneliner}
            </div>
            <div style={{
              fontSize: '11px', color: colors.textMuted,
              fontFamily: 'monospace', marginTop: '6px',
              letterSpacing: '0.06em',
            }}>
              Run as root on the target VM. Supports apt, dnf, or yum systems and requires python3 plus curl or wget.
            </div>
          </>
        ) : (
          <div style={{
            padding: '24px 20px',
            border: `1px dashed ${colors.border}`,
            background: glassBg(0.3),
            textAlign: 'center',
            color: colors.textMuted,
            fontSize: '12px',
            fontFamily: 'monospace',
          }}>
            {!urlValid
              ? 'Enter a valid server URL above'
              : expiresIn > 0
                ? 'This browser no longer has the plaintext key. Generate a new key to refresh the installer.'
                : 'Generate a registration key in Step 1 to see the install command'}
          </div>
        )}
      </div>

      {/* Step 4 — Full script */}
      {script && (
        <div style={{ marginBottom: '28px' }}>
          <SectionHeader right={
            <div style={{ display: 'flex', gap: '8px' }}>
              <CopyButton text={script} label="Copy Script" />
              <button
                onClick={downloadScript}
                style={{
                  background: `${colors.primary}12`,
                  border: `1px solid ${colors.primary}66`,
                  color: colors.primary,
                  cursor: 'pointer',
                  padding: '6px 16px',
                  fontSize: '11px',
                  fontFamily: "'Electrolize', monospace",
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  textShadow: glowText(colors.primary, 3),
                  transition: 'all 0.2s',
                  clipPath: 'polygon(4px 0%, 100% 0%, calc(100% - 4px) 100%, 0% 100%)',
                  whiteSpace: 'nowrap',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.background = `${colors.primary}22`
                  e.currentTarget.style.boxShadow = `0 0 12px ${colors.primary}33`
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = `${colors.primary}12`
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                ↓ Download .sh
              </button>
            </div>
          }>
            4. Full Install Script
          </SectionHeader>

          <div style={{
            background: 'rgba(1,8,10,0.95)',
            border: `1px solid ${colors.border}`,
            position: 'relative',
            maxHeight: '420px',
            overflow: 'auto',
          }}>
            <div style={{
              position: 'absolute', top: 0, left: 0, right: 0, height: '1px',
              background: `linear-gradient(90deg, transparent, ${colors.primary}55, transparent)`,
              zIndex: 1,
            }} />
            {/* Scanline */}
            <div style={{
              position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 1,
              background: `repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.04) 2px,rgba(0,0,0,0.04) 4px)`,
            }} />
            <pre style={{
              margin: 0,
              padding: '16px 20px',
              fontFamily: "'Courier New', Courier, monospace",
              fontSize: '12px',
              color: colors.textDim,
              lineHeight: 1.7,
              position: 'relative',
              zIndex: 2,
            }}>
              {script.split('\n').map((line, i) => {
                const isComment = line.trim().startsWith('#')
                const isKey = /^(AGENT_ID|SERVER_URL|REGISTER_KEY|AGENT_DIR|CONFIG_DIR|set )/.test(line.trim())
                const color = isComment ? colors.textMuted
                            : isKey     ? colors.warn
                            : line.includes('echo') ? colors.success
                            : colors.textDim
                return (
                  <span key={i} style={{ display: 'block', color }}>
                    {line || '\u00A0'}
                  </span>
                )
              })}
            </pre>
          </div>
        </div>
      )}

      <div style={{ marginBottom: '28px' }}>
        <SectionHeader right={haAddonConfig ? <CopyButton text={haAddonConfig} label="Copy Add-on Config" /> : undefined}>
          {script ? '5' : '4'}. Home Assistant OS Add-on
        </SectionHeader>
        <Card style={{ padding: '20px 22px' }}>
          <div style={{
            fontSize: '12px',
            color: colors.text,
            fontFamily: "'Electrolize', monospace",
            letterSpacing: '0.05em',
            lineHeight: 1.7,
            marginBottom: '16px',
          }}>
            Use this if you run Home Assistant OS on a Raspberry Pi or appliance install. PatchPilot now provides the
            repository URL and the complete add-on configuration, including the decoded PEM certificate for self-signed TLS.
          </div>

          <div style={{ display: 'grid', gap: '14px' }}>
            <div>
              <div style={{
                fontSize: '10px',
                color: colors.textMuted,
                fontFamily: "'Orbitron', sans-serif",
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                marginBottom: '8px',
              }}>
                Add-on Repository
              </div>
              <div style={{
                background: 'rgba(1,8,10,0.95)',
                border: `1px solid ${colors.border}`,
                padding: '14px 16px',
                display: 'flex',
                gap: '10px',
                alignItems: 'center',
                flexWrap: 'wrap',
              }}>
                <code style={{
                  flex: 1,
                  minWidth: '220px',
                  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  fontSize: '12px',
                  color: colors.primary,
                  textShadow: glowText(colors.primary, 3),
                  overflowWrap: 'anywhere',
                }}>
                  {haRepoUrl}
                </code>
                <CopyButton text={haRepoUrl} label="Copy URL" />
              </div>
            </div>

            <div>
              <div style={{
                fontSize: '10px',
                color: colors.textMuted,
                fontFamily: "'Orbitron', sans-serif",
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                marginBottom: '8px',
              }}>
                Add-on Configuration
              </div>
              {haAddonConfig ? (
                <>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '8px' }}>
                    <CopyButton text={haAddonConfig} label="Copy Add-on Config" />
                  </div>
                  <div style={{
                    background: 'rgba(1,8,10,0.95)',
                    border: `1px solid ${colors.border}`,
                    position: 'relative',
                    maxHeight: '360px',
                    overflow: 'auto',
                  }}>
                    <div style={{
                      position: 'absolute', top: 0, left: 0, right: 0, height: '1px',
                      background: `linear-gradient(90deg, transparent, ${colors.primary}55, transparent)`,
                    }} />
                    <pre style={{
                      margin: 0,
                      padding: '16px 20px',
                      fontFamily: "'Courier New', Courier, monospace",
                      fontSize: '12px',
                      color: colors.textDim,
                      lineHeight: 1.7,
                      whiteSpace: 'pre-wrap',
                      overflowWrap: 'anywhere',
                    }}>
                      {haAddonConfig}
                    </pre>
                  </div>
                  <div style={{
                    fontSize: '11px',
                    color: colors.textMuted,
                    fontFamily: 'monospace',
                    marginTop: '6px',
                    letterSpacing: '0.04em',
                  }}>
                    Paste this into the add-on configuration in Home Assistant. The certificate is already decoded to PEM format.
                  </div>
                </>
              ) : (
                <div style={{
                  padding: '20px',
                  border: `1px dashed ${colors.border}`,
                  background: glassBg(0.3),
                  textAlign: 'center',
                  color: colors.textMuted,
                  fontSize: '12px',
                  fontFamily: 'monospace',
                }}>
                  Generate a registration key above to unlock the ready-to-paste Home Assistant add-on configuration.
                </div>
              )}
            </div>
          </div>
        </Card>
      </div>

      {/* Manual instructions */}
      <div>
        <SectionHeader>{script ? '6' : '5'}. Manual Steps</SectionHeader>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {[
            { n: '1', text: 'Generate a registration key above (valid 5 min)' },
            { n: '2', text: 'Set the server URL to the internal address your VMs can reach' },
            { n: '3', text: 'Copy the one-liner or download the script and run as root on the target VM' },
            { n: '4', text: 'For Home Assistant OS, add the GitHub repository in the Add-on Store and paste the generated add-on config' },
            { n: '5', text: 'The VM or Home Assistant instance appears in the dashboard within ~30 seconds' },
          ].map(({ n, text }) => (
            <div key={n} style={{
              display: 'flex',
              gap: '14px',
              padding: '14px 18px',
              border: `1px solid ${colors.border}`,
              background: glassBg(0.5),
              alignItems: 'center',
            }}>
              <div style={{
                width: '22px', height: '22px', flexShrink: 0,
                border: `1px solid ${colors.primary}66`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontFamily: "'Orbitron', sans-serif",
                fontSize: '10px', color: colors.primary,
                textShadow: glowText(colors.primary, 4),
                boxShadow: `inset 0 0 8px ${colors.primary}10`,
              }}>
                {n}
              </div>
              <div style={{
                fontSize: '12px', color: colors.text,
                fontFamily: "'Electrolize', monospace",
                letterSpacing: '0.05em',
              }}>
                {text}
              </div>
            </div>
          ))}
        </div>
      </div>
      </>}
    </div>
  )
}
