import { useState, useEffect, useRef, useCallback } from 'react'
import { colors, glow, glowText, glowStrong, glassBg } from '../theme'
import { PageHeader, SectionHeader } from '../components/SectionHeader'
import { Card } from '../components/Card'
import { Button } from '../components/Button'
import { api } from '../api/client'

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

function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)

  const copy = () => {
    copyToClipboard(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const c = copied ? colors.success : colors.primary
  return (
    <button
      onClick={copy}
      style={{
        background: `${c}12`,
        border: `1px solid ${c}66`,
        color: c,
        cursor: 'pointer',
        padding: '6px 16px',
        fontSize: '11px',
        fontFamily: "'Electrolize', monospace",
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        textShadow: glowText(c, 3),
        transition: 'all 0.2s',
        clipPath: 'polygon(4px 0%, 100% 0%, calc(100% - 4px) 100%, 0% 100%)',
        whiteSpace: 'nowrap',
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
    if (!registerKey) return
    timerRef.current = setInterval(() => {
      setExpiresIn(prev => {
        if (prev <= 1) {
          setRegisterKey('')
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [registerKey, setRegisterKey, setExpiresIn])

  const generate = async () => {
    setGenerating(true)
    try {
      const r = await api.generateRegisterKey()
      setRegisterKey(r.key)
      setExpiresIn(r.expires_in)
    } catch (e) {
      console.error(e)
    } finally {
      setGenerating(false)
    }
  }

  const key = registerKey

  const copyKey = () => {
    if (key) {
      copyToClipboard(key)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
  const pct = key ? (expiresIn / 300) * 100 : 0

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

        {key ? (
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

function buildScript(serverUrl: string, agentId: string, registerKey: string): string {
  // Build as array to avoid template-literal escaping nightmare with shell ${}
  const D = '$'  // shell dollar sign
  const lines = [
    '#!/bin/bash',
    '# PatchPilot Agent Installer',
    `# Server: ${serverUrl}`,
    'set -e',
    '',
    `AGENT_ID="${D}{PATCHPILOT_AGENT_ID:-${agentId || `${D}(hostname)`}}"`,
    `SERVER_URL="${serverUrl}"`,
    `REGISTER_KEY="${registerKey}"`,
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
    'else',
    '  echo "ERROR: No supported package manager found (requires apt/apt-get)" >&2',
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
    '# ── SSL: fetch CA certificate if server uses HTTPS ──────────────────────────',
    'CURL_OPTS=""',
    'WGET_OPTS=""',
    `if echo "${D}SERVER_URL" | grep -qi '^https://'; then`,
    '  echo "[patchpilot] HTTPS server detected — fetching CA certificate..."',
    '  if command -v curl &>/dev/null; then',
    `    curl -fsSLk "${D}SERVER_URL/agent/ca.pem" -o "${D}CONFIG_DIR/ca.pem" 2>/dev/null || true`,
    '  else',
    `    wget --no-check-certificate -qO "${D}CONFIG_DIR/ca.pem" "${D}SERVER_URL/agent/ca.pem" 2>/dev/null || true`,
    '  fi',
    `  if [ -s "${D}CONFIG_DIR/ca.pem" ]; then`,
    `    echo "[patchpilot] CA certificate installed at ${D}CONFIG_DIR/ca.pem"`,
    `    CURL_OPTS="--cacert ${D}CONFIG_DIR/ca.pem"`,
    `    WGET_OPTS="--ca-certificate=${D}CONFIG_DIR/ca.pem"`,
    '  else',
    '    echo "[patchpilot] WARNING: Could not fetch CA cert — falling back to insecure mode"',
    '    CURL_OPTS="-k"',
    '    WGET_OPTS="--no-check-certificate"',
    '  fi',
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

  // Load settings + active key in parallel on mount
  useEffect(() => {
    Promise.all([
      api.settings().then((s: any) => {
        // Prefer agent_url (HTTP, agent port) over internal_url (UI port, may be HTTPS)
        if (s.agent_url) setInternalUrl(s.agent_url)
        else if (s.internal_url) setInternalUrl(s.internal_url)
      }).catch(() => {}),
      api.registerKeyStatus().then(r => {
        if (r.active && r.key) {
          setRegisterKey(r.key)
          setExpiresIn(r.expires_in)
        } else if (r.active) {
          // Key is hashed in DB — plaintext no longer available
          setRegisterKey('')
          setExpiresIn(r.expires_in)
        }
      }).catch(() => {}),
    ]).finally(() => setPageReady(true))
  }, [])

  // Default: server-detected internal IP:port. User can override.
  const effectiveUrl = serverUrl || internalUrl


  const agentIdError = agentId.length > 0 && !AGENT_ID_RE.test(agentId)
    ? 'Only letters, numbers, dots, hyphens and underscores allowed (max 64)'
    : null
  const safeAgentId = AGENT_ID_RE.test(agentId) ? agentId : ''

  const urlValid = SERVER_URL_RE.test(effectiveUrl)
  const isHttps = effectiveUrl.toLowerCase().startsWith('https://')
  const curlFlags = isHttps ? '-fsSLk' : '-fsSL'
  const oneliner = urlValid
    ? `curl ${curlFlags} ${effectiveUrl}/agent/install.sh | sudo PATCHPILOT_SERVER=${effectiveUrl} PATCHPILOT_REGISTER_KEY=${registerKey || '<KEY>'}${safeAgentId ? ` PATCHPILOT_AGENT_ID=${safeAgentId}` : ''} bash`
    : ''

  const script = urlValid
    ? buildScript(effectiveUrl, safeAgentId, registerKey)
    : ''

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
        <SectionHeader right={oneliner && registerKey ? <CopyButton text={oneliner} label="Copy Command" /> : undefined}>
          3. Quick Install (One-Liner)
        </SectionHeader>
        {oneliner && registerKey ? (
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
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
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
              Run as root on the target VM. Requires python3 and curl or wget.
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
            {!urlValid ? 'Enter a valid server URL above' : 'Generate a registration key in Step 1 to see the install command'}
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

      {/* Manual instructions */}
      <div>
        <SectionHeader>{script ? '5' : '4'}. Manual Steps</SectionHeader>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {[
            { n: '1', text: 'Generate a registration key above (valid 5 min)' },
            { n: '2', text: 'Set the server URL to the internal address your VMs can reach' },
            { n: '3', text: 'Copy the one-liner or download the script and run as root on the target VM' },
            { n: '4', text: 'The VM appears in the dashboard within ~30 seconds' },
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
