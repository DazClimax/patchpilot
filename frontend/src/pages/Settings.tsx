import React, { useEffect, useRef, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { api, Settings, auth } from '../api/client'
import { Animator, FrameCorners } from '@arwes/react'
import { colors, glow, glowText, glassBg } from '../theme'
import { Card } from '../components/Card'
import { ConfirmModal } from '../components/ConfirmModal'
import { Button } from '../components/Button'
import { PageHeader, SectionHeader } from '../components/SectionHeader'
import { Dropdown } from '../components/Dropdown'
import { useToast } from '../components/Toast'

// ---------------------------------------------------------------------------
// Style helpers (identical pattern to Schedule.tsx)
// ---------------------------------------------------------------------------

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  background: colors.bg,
  border: `1px solid ${colors.border}`,
  color: colors.text,
  fontFamily: "'Electrolize', monospace",
  fontSize: '13px',
  outline: 'none',
  letterSpacing: '0.04em',
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '10px',
  letterSpacing: '0.2em',
  textTransform: 'uppercase',
  color: colors.textMuted,
  marginBottom: '6px',
  fontFamily: "'Orbitron', sans-serif",
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Field({
  label,
  name,
  value,
  onChange,
  placeholder = '',
  type = 'text',
}: {
  label: string
  name: string
  value: string
  onChange: (name: string, value: string) => void
  placeholder?: string
  type?: string
}) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <input
        style={inputStyle}
        type={type}
        name={name}
        value={value}
        placeholder={placeholder}
        onChange={e => onChange(name, e.target.value)}
        autoComplete="off"
      />
    </div>
  )
}

function Toggle({
  label,
  name,
  value,
  onChange,
}: {
  label: string
  name: string
  value: string
  onChange: (name: string, value: string) => void
}) {
  const on = value === '1'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label={label}
        onClick={() => onChange(name, on ? '0' : '1')}
        style={{
          width: '44px',
          height: '22px',
          borderRadius: '11px',
          border: `1px solid ${on ? colors.primary : colors.border}`,
          background: on ? `${colors.primary}22` : 'transparent',
          cursor: 'pointer',
          position: 'relative',
          transition: 'all 0.2s ease',
          flexShrink: 0,
        }}
      >
        <span style={{
          position: 'absolute',
          top: '3px',
          left: on ? '22px' : '3px',
          width: '14px',
          height: '14px',
          borderRadius: '50%',
          background: on ? colors.primary : colors.textMuted,
          boxShadow: on ? glow(colors.primary, 4) : 'none',
          transition: 'all 0.2s ease',
        }} />
      </button>
      <span style={{
        fontSize: '12px',
        fontFamily: "'Electrolize', monospace",
        letterSpacing: '0.08em',
        color: on ? colors.text : colors.textDim,
      }}>
        {label}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Toast / feedback message
// ---------------------------------------------------------------------------

// Toast: uses global useToast() from components/Toast.tsx

// ---------------------------------------------------------------------------
// Default / empty settings
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Telegram Setup Guide (expandable on click)
// ---------------------------------------------------------------------------

function TelegramGuide() {
  const [open, setOpen] = useState(false)
  const steps = [
    { n: '1', text: 'Open Telegram and search for @BotFather' },
    { n: '2', text: 'Send /newbot — choose a name and username (must end in "bot")' },
    { n: '3', text: 'Copy the API token BotFather gives you → paste in "Bot Token" below' },
    { n: '4', text: 'Start a chat with your bot (send any message to it)' },
    { n: '5', text: 'Open: api.telegram.org/bot<YOUR_TOKEN>/getUpdates in a browser' },
    { n: '6', text: 'Find "chat":{"id": ...} — that number is your Chat ID → paste below' },
    { n: '7', text: 'For groups: add the bot as admin, then use the group chat ID (starts with -100...)' },
    { n: '8', text: 'Hit "Send Test" to verify everything works' },
  ]

  return (
    <div style={{ marginBottom: '16px' }}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '0',
          color: open ? colors.primary : colors.textMuted,
          fontFamily: "'Electrolize', monospace",
          fontSize: '11px',
          letterSpacing: '0.1em',
          textShadow: open ? glowText(colors.primary, 3) : 'none',
          transition: 'color 0.15s',
        }}
      >
        <span style={{
          fontSize: '10px',
          border: `1px solid ${open ? colors.primary + '66' : colors.border}`,
          width: '16px', height: '16px',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          transition: 'border-color 0.15s',
        }}>
          {open ? '▲' : '▼'}
        </span>
        How to set up a Telegram bot
      </button>
      {open && (
        <div style={{
          marginTop: '12px',
          padding: '14px 16px',
          background: `${colors.primary}06`,
          border: `1px solid ${colors.primary}22`,
          animation: 'pp-fadein 0.2s ease both',
        }}>
          {steps.map(s => (
            <div key={s.n} style={{
              display: 'flex',
              gap: '12px',
              marginBottom: '8px',
              fontSize: '11px',
              fontFamily: "'Electrolize', monospace",
              letterSpacing: '0.04em',
            }}>
              <span style={{
                flexShrink: 0,
                width: '18px', height: '18px',
                background: `${colors.primary}18`,
                border: `1px solid ${colors.primary}44`,
                color: colors.primary,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '9px', fontWeight: 700,
              }}>
                {s.n}
              </span>
              <span style={{ color: colors.textDim, lineHeight: 1.5 }}>{s.text}</span>
            </div>
          ))}
          <div style={{
            marginTop: '10px',
            paddingTop: '10px',
            borderTop: `1px solid ${colors.border}`,
            fontSize: '10px',
            color: colors.textMuted,
            fontFamily: "'Electrolize', monospace",
          }}>
            Bot commands available: /help /status /vms /jobs /patch /reboot /updates
          </div>
        </div>
      )}
    </div>
  )
}

const SMTP_SECURITY_OPTIONS = [
  { value: 'starttls', label: 'STARTTLS (Port 587)' },
  { value: 'ssl',      label: 'SSL / TLS (Port 465)' },
  { value: 'plain',    label: 'Plain + Login (Port 25)' },
  { value: 'none',     label: 'Plain / No Auth (Port 25)' },
]

const SMTP_DEFAULT_PORTS: Record<string, string> = {
  starttls: '587',
  ssl:      '465',
  plain:    '25',
  none:     '25',
}

const EMPTY: Settings = {
  telegram_token: '',
  telegram_chat_id: '',
  email_enabled: '1',
  smtp_host: '',
  smtp_port: '587',
  smtp_security: 'starttls',
  smtp_user: '',
  smtp_password: '',
  smtp_to: '',
  notify_offline: '1',
  notify_offline_minutes: '10',
  notify_patches: '1',
  notify_failures: '1',
  telegram_enabled: '1',
  telegram_notify_offline: '1',
  telegram_notify_patches: '1',
  telegram_notify_failures: '1',
  telegram_notify_success: '1',
  server_port: '8443',
  agent_port: '8050',
  agent_ssl: '0',
  agent_url: '',
  ssl_certfile: '',
  ssl_keyfile: '',
  ssl_enabled: false as any,
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function SettingsPage() {
  const [form, setForm] = useState<Settings>(EMPTY)
  const [savedForm, setSavedForm] = useState<Settings>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<'telegram' | 'email' | null>(null)
  const [restarting, setRestarting] = useState(false)
  const portPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [restartPort, setRestartPort] = useState<string | null>(null)
  const [tab, setTab] = useState<'notifications' | 'server'>('notifications')
  const { showToast } = useToast()

  const isDirty = JSON.stringify(form) !== JSON.stringify(savedForm)

  const load = useCallback(async () => {
    try {
      const data = await api.settings()
      const merged = { ...EMPTY, ...data }
      setForm(merged)
      setSavedForm(merged)
    } catch {
      showToast('Error loading settings', 'error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Cleanup port-migration polling on unmount
  useEffect(() => {
    return () => { if (portPollRef.current) clearInterval(portPollRef.current) }
  }, [])

  // Warn on navigation with unsaved changes
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (isDirty) { e.preventDefault(); e.returnValue = '' }
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isDirty])

  const handleChange = (name: string, value: string) => {
    setForm(f => ({ ...f, [name]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      // Strip computed/non-DB fields before saving
      const { ssl_enabled, ssl_certfile, ssl_keyfile, internal_url, agent_url, ...saveable } = form as any
      const result = await api.saveSettings(saveable)
      if (result.restart_pending && result.new_port) {
        const newPort = result.new_port
        setRestartPort(newPort)
        setRestarting(true)
        const protocol = saveable.ssl_certfile ? 'https' : window.location.protocol.replace(':', '')
        const origin = `${protocol}://${window.location.hostname}:${newPort}`
        const redirectUrl = `${origin}/#pp-key=${encodeURIComponent(auth.getKey())}`
        // Wait for server to restart, then redirect
        const timer = setTimeout(() => {
          portPollRef.current = null
          window.location.href = redirectUrl
        }, 6000)
        portPollRef.current = timer as any
      } else {
        setSavedForm({ ...form })
        showToast('Settings saved', 'success')
      }
    } catch {
      showToast('Error saving settings', 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async (channel: 'telegram' | 'email') => {
    setTesting(channel)
    try {
      await api.testNotification(channel)
      showToast(`Test message sent via ${channel === 'telegram' ? 'Telegram' : 'E-Mail'}`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      showToast(`Test failed: ${msg}`, 'error')
    } finally {
      setTesting(null)
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 'clamp(16px, 4vw, 32px)', maxWidth: '1400px' }}>
        <PageHeader>Settings</PageHeader>
        {[1, 2, 3].map(i => (
          <div key={i} style={{
            height: '120px',
            marginBottom: '20px',
            background: glassBg(0.4),
            border: `1px solid ${colors.border}`,
            animation: 'pp-pulse 1.5s ease-in-out infinite',
          }} />
        ))}
      </div>
    )
  }

  const divider: React.CSSProperties = {
    borderBottom: `1px solid ${colors.border}`,
    margin: '24px 0',
  }

  return (
    <div style={{ padding: 'clamp(16px, 4vw, 32px)', maxWidth: '1400px' }}>
      <PageHeader>Settings</PageHeader>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0', marginBottom: '24px', borderBottom: `1px solid ${colors.border}` }}>
        {(['notifications', 'server'] as const).map(t => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              padding: '10px 24px',
              fontFamily: "'Orbitron', sans-serif",
              fontSize: '11px',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: tab === t ? colors.primary : colors.textMuted,
              textShadow: tab === t ? glowText(colors.primary, 4) : 'none',
              borderBottom: tab === t ? `2px solid ${colors.primary}` : '2px solid transparent',
              marginBottom: '-1px',
              transition: 'all 0.15s',
            }}
          >
            {t === 'notifications' ? 'Notifications' : 'Server'}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit}>

        {/* ================================================================== */}
        {/* TAB: Notifications                                                  */}
        {/* ================================================================== */}
        {tab === 'notifications' && <>

        {/* ------------------------------------------------------------------ */}
        {/* Telegram                                                             */}
        {/* ------------------------------------------------------------------ */}
        <Card style={{ marginBottom: '20px' }}>
          <SectionHeader right={
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={testing === 'telegram' || form.telegram_enabled !== '1'}
              onClick={() => handleTest('telegram')}
            >
              {testing === 'telegram' ? 'SENDING...' : 'SEND TEST'}
            </Button>
          }>
            Telegram
          </SectionHeader>

          <TelegramGuide />

          <Toggle
            label="Enable Telegram Notifications"
            name="telegram_enabled"
            value={form.telegram_enabled}
            onChange={handleChange}
          />

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '16px',
            marginTop: '12px',
            opacity: form.telegram_enabled === '1' ? 1 : 0.4,
            pointerEvents: form.telegram_enabled === '1' ? 'auto' : 'none',
            transition: 'opacity 0.2s ease',
          }}>
            <Field
              label="Bot Token"
              name="telegram_token"
              value={form.telegram_token}
              onChange={handleChange}
              placeholder="123456:ABC-DEF..."
              type="password"
            />
            <Field
              label="Chat ID"
              name="telegram_chat_id"
              value={form.telegram_chat_id}
              onChange={handleChange}
              placeholder="-100123456789"
            />
          </div>

          <div style={{
            marginTop: '14px', paddingTop: '14px', borderTop: `1px solid ${colors.border}`,
            opacity: form.telegram_enabled === '1' ? 1 : 0.4,
            pointerEvents: form.telegram_enabled === '1' ? 'auto' : 'none',
          }}>
            <div style={{ fontSize: '10px', letterSpacing: '0.15em', color: colors.textMuted, fontFamily: "'Orbitron', sans-serif", marginBottom: '10px' }}>
              TELEGRAM EVENTS
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <Toggle label="VM offline" name="telegram_notify_offline" value={form.telegram_notify_offline} onChange={handleChange} />
              <Toggle label="Updates available / Reboot required" name="telegram_notify_patches" value={form.telegram_notify_patches} onChange={handleChange} />
              <Toggle label="Job failed" name="telegram_notify_failures" value={form.telegram_notify_failures} onChange={handleChange} />
              <Toggle label="Job completed" name="telegram_notify_success" value={form.telegram_notify_success} onChange={handleChange} />
            </div>
          </div>
        </Card>

        {/* ------------------------------------------------------------------ */}
        {/* E-Mail / SMTP                                                        */}
        {/* ------------------------------------------------------------------ */}
        <Card style={{ marginBottom: '20px' }}>
          <SectionHeader right={
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={testing === 'email' || form.email_enabled !== '1'}
              onClick={() => handleTest('email')}
            >
              {testing === 'email' ? 'SENDING...' : 'SEND TEST'}
            </Button>
          }>
            E-Mail (SMTP)
          </SectionHeader>

          <Toggle
            label="Enable Email Notifications"
            name="email_enabled"
            value={form.email_enabled}
            onChange={handleChange}
          />

          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px',
            marginTop: '14px',
            opacity: form.email_enabled === '1' ? 1 : 0.4,
            pointerEvents: form.email_enabled === '1' ? 'auto' : 'none',
          }}>
            <Field
              label="SMTP Host"
              name="smtp_host"
              value={form.smtp_host}
              onChange={handleChange}
              placeholder="smtp.example.com"
            />
            <div>
              <label style={labelStyle}>Security / Auth</label>
              <Dropdown
                value={form.smtp_security}
                onChange={v => setForm(f => ({
                  ...f,
                  smtp_security: v,
                  smtp_port: f.smtp_port === SMTP_DEFAULT_PORTS[f.smtp_security]
                    ? SMTP_DEFAULT_PORTS[v]
                    : f.smtp_port,
                }))}
                options={SMTP_SECURITY_OPTIONS}
              />
            </div>
            <Field
              label="Port"
              name="smtp_port"
              value={form.smtp_port}
              onChange={handleChange}
              placeholder={SMTP_DEFAULT_PORTS[form.smtp_security] ?? '587'}
            />
            <Field
              label="Username"
              name="smtp_user"
              value={form.smtp_user}
              onChange={handleChange}
              placeholder="alerts@example.com"
            />
            <Field
              label="Password"
              name="smtp_password"
              value={form.smtp_password}
              onChange={handleChange}
              placeholder={form.smtp_password === '***' ? '(unchanged)' : ''}
              type="password"
            />
            <Field
              label="Recipient"
              name="smtp_to"
              value={form.smtp_to}
              onChange={handleChange}
              placeholder="admin@example.com"
            />
          </div>

          <div style={{
            marginTop: '14px', paddingTop: '14px', borderTop: `1px solid ${colors.border}`,
            opacity: form.email_enabled === '1' ? 1 : 0.4,
            pointerEvents: form.email_enabled === '1' ? 'auto' : 'none',
          }}>
            <div style={{ fontSize: '10px', letterSpacing: '0.15em', color: colors.textMuted, fontFamily: "'Orbitron', sans-serif", marginBottom: '10px' }}>
              EMAIL EVENTS
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
                <Toggle label="VM offline after" name="notify_offline" value={form.notify_offline} onChange={handleChange} />
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <input
                    type="number" min="1" max="120"
                    value={form.notify_offline_minutes}
                    onChange={e => handleChange('notify_offline_minutes', e.target.value)}
                    disabled={form.notify_offline === '0'}
                    style={{
                      width: '52px', padding: '3px 6px', background: colors.bg,
                      border: `1px solid ${form.notify_offline === '1' ? colors.border : colors.border + '44'}`,
                      color: form.notify_offline === '1' ? colors.text : colors.textMuted,
                      fontFamily: "'Electrolize', monospace", fontSize: '12px', outline: 'none', textAlign: 'center',
                    }}
                  />
                  <span style={{ fontSize: '11px', color: colors.textMuted, fontFamily: "'Electrolize', monospace" }}>min</span>
                </div>
              </div>
              <Toggle label="Updates available / Reboot required" name="notify_patches" value={form.notify_patches} onChange={handleChange} />
              <Toggle label="Patch job failed" name="notify_failures" value={form.notify_failures} onChange={handleChange} />
            </div>
          </div>
        </Card>

        </>}

        {/* ================================================================== */}
        {/* TAB: Server                                                         */}
        {/* ================================================================== */}
        {tab === 'server' && <>

        {/* ------------------------------------------------------------------ */}
        {/* Server                                                               */}
        {/* ------------------------------------------------------------------ */}
        <Card style={{ marginBottom: '20px' }}>
          <SectionHeader>Server</SectionHeader>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '24px', flexWrap: 'wrap' }}>
            <div style={{ width: '140px', flexShrink: 0 }}>
              <Field
                label="UI Port"
                name="server_port"
                value={form.server_port}
                onChange={handleChange}
                placeholder="8443"
              />
            </div>
            <div style={{ width: '140px', flexShrink: 0 }}>
              <Field
                label="Agent Port"
                name="agent_port"
                value={form.agent_port}
                onChange={handleChange}
                placeholder="8050"
              />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', paddingTop: '22px' }}>
              <Toggle
                label="Agent SSL"
                name="agent_ssl"
                value={form.agent_ssl}
                onChange={handleChange}
              />
            </div>
            <p style={{
              margin: '14px 0 0',
              fontSize: '11px',
              fontFamily: "'Electrolize', monospace",
              color: colors.textMuted,
              letterSpacing: '0.04em',
              lineHeight: 1.6,
              whiteSpace: 'normal',
            }}>
              UI port supports HTTPS via SSL section below. Agent SSL uses the same certificate.<br />
              Agents migrate automatically on their next heartbeat.
            </p>
          </div>
        </Card>

        {/* ------------------------------------------------------------------ */}
        {/* SSL / HTTPS                                                          */}
        {/* ------------------------------------------------------------------ */}
        <SslSection />

        </>}

        {/* ------------------------------------------------------------------ */}
        {/* Save button (always visible)                                         */}
        {/* ------------------------------------------------------------------ */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Button type="submit" disabled={saving || !isDirty}>
            {saving ? 'SAVING...' : isDirty ? '● SAVE SETTINGS' : 'SAVE SETTINGS'}
          </Button>
          {isDirty && (
            <Button type="button" variant="ghost" onClick={() => setForm(savedForm)}>
              ↩ UNDO
            </Button>
          )}
          {isDirty && (
            <span style={{
              fontSize: '11px',
              color: colors.warn,
              fontFamily: "'Electrolize', monospace",
              letterSpacing: '0.06em',
            }}>
              Unsaved changes
            </span>
          )}
        </div>
      </form>

      {/* Toasts rendered by global ToastProvider */}

      {restarting && (() => {
        const proto = window.location.protocol.replace(':', '')
        const newUrl = `${window.location.protocol}//${window.location.hostname}:${restartPort}`
        const stillPolling = portPollRef.current !== null
        return (
          <div style={{
            position: 'fixed', inset: 0,
            background: `${colors.bg}ee`,
            backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: '20px',
            zIndex: 10000, animation: 'pp-fadein 0.3s ease both',
          }}>
            {stillPolling ? (
              <>
                <div style={{
                  width: '36px', height: '36px', borderRadius: '50%',
                  border: `2px solid ${colors.primary}22`,
                  borderTopColor: colors.primary,
                  animation: 'pp-spin 0.8s linear infinite',
                  boxShadow: `0 0 16px ${colors.primary}44`,
                }} />
                <div style={{
                  fontFamily: "'Orbitron', sans-serif", fontSize: '13px',
                  letterSpacing: '0.22em', textTransform: 'uppercase',
                  color: colors.primary, textShadow: `0 0 8px ${colors.primary}88`,
                }}>
                  Server Restarting
                </div>
                <div style={{
                  fontFamily: "'Electrolize', monospace", fontSize: '11px',
                  letterSpacing: '0.1em', color: colors.textMuted,
                }}>
                  Redirecting to port {restartPort} …
                </div>
              </>
            ) : (
              <>
                <div style={{
                  fontFamily: "'Orbitron', sans-serif", fontSize: '13px',
                  letterSpacing: '0.22em', textTransform: 'uppercase',
                  color: colors.primary, textShadow: `0 0 8px ${colors.primary}88`,
                }}>
                  Server Restarted
                </div>
                <div style={{
                  fontFamily: "'Electrolize', monospace", fontSize: '12px',
                  color: colors.text, textAlign: 'center', lineHeight: 1.8,
                }}>
                  The server is now running on port {restartPort}.
                </div>
                <a
                  href={`${newUrl}/#pp-key=${encodeURIComponent(auth.getKey())}`}
                  style={{
                    fontFamily: "'Orbitron', sans-serif", fontSize: '12px',
                    letterSpacing: '0.12em', textTransform: 'uppercase',
                    color: colors.primary, textShadow: `0 0 6px ${colors.primary}66`,
                    padding: '10px 24px',
                    border: `1px solid ${colors.primary}44`,
                    textDecoration: 'none',
                    transition: 'all 0.15s',
                  }}
                >
                  Open on port {restartPort} →
                </a>
              </>
            )}
          </div>
        )
      })()}
    </div>
  )
}


// ---------------------------------------------------------------------------
// SSL / HTTPS Section
// ---------------------------------------------------------------------------
type DeployAgent = { agent_id: string; hostname: string; status: string; phase: string; output: string; finished: string | null; online: boolean }
type DeployStatus = { agents: DeployAgent[]; total: number; total_online: number; completed: number }

const CERT_VALIDITY_OPTIONS = [
  { value: '1', label: '1 Year' },
  { value: '3', label: '3 Years' },
  { value: '5', label: '5 Years' },
  { value: '10', label: '10 Years' },
]

function DeployModal({
  deployStatus,
  ssl,
  busy,
  setBusy,
  onClose,
  onRetry,
  onEnableHttps,
}: {
  deployStatus: DeployStatus | null
  ssl: { enabled: boolean; certfile: string; keyfile: string; info: any } | null
  busy: boolean
  setBusy: (b: boolean) => void
  onClose: () => void
  onRetry: () => void
  onEnableHttps: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  // Deployment is "done" when all online agents finished — offline ones will catch up later
  const onlineTotal = deployStatus ? (deployStatus.total_online ?? deployStatus.total) : 0
  const allOnlineDone = deployStatus != null && onlineTotal > 0 && deployStatus.completed >= onlineTotal
  // Also treat as "done" if polling stopped (timeout or all done) — busy=false signals this
  const isDone = allOnlineDone || (deployStatus != null && !busy)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isDone) onClose()
      if (e.key === 'Tab' && panelRef.current) {
        const focusable = panelRef.current.querySelectorAll<HTMLElement>('button, [tabindex]:not([tabindex="-1"])')
        if (focusable.length === 0) return
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isDone, onClose])

  const hasFailed = deployStatus?.agents.some(a => a.status === 'failed') ?? false
  const barColor = hasFailed ? colors.danger : isDone ? colors.success : colors.primary

  return createPortal(
    <div
      onClick={e => { if (e.target === e.currentTarget && isDone) onClose() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 10000,
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        background: `${colors.bg}ee`,
        backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
      }}
    >
      <Animator active>
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby="ssl-deploy-title"
          onClick={e => e.stopPropagation()}
          style={{
            position: 'relative',
            width: 'min(520px, 92vw)',
            background: glassBg(0.97),
            backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
            boxShadow: `0 0 60px ${colors.primary}18, 0 0 120px rgba(0,0,0,0.95), inset 0 0 40px ${colors.primary}05`,
            animation: 'pp-fadein 0.22s ease both',
          }}
        >
          <FrameCorners
            strokeWidth={1.5}
            cornerLength={16}
            styled={false}
            positioned
            style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 1, color: colors.primary }}
          />
          <div style={{
            position: 'absolute', top: 0, left: 0, right: 0, height: '1px',
            background: `linear-gradient(90deg, transparent, ${colors.primary}99, transparent)`,
            zIndex: 2,
          }} />

          {/* Header */}
          <div style={{
            padding: '16px 22px', borderBottom: `1px solid ${colors.border}`,
            display: 'flex', alignItems: 'center', gap: '10px',
            position: 'relative', zIndex: 2,
          }}>
            <div style={{ width: '2px', height: '14px', flexShrink: 0, background: colors.primary, boxShadow: `0 0 8px ${colors.primary}` }} />
            <span id="ssl-deploy-title" style={{
              fontFamily: "'Orbitron', sans-serif", fontSize: '11px',
              letterSpacing: '0.22em', color: colors.primary,
              textShadow: glowText(colors.primary, 4), textTransform: 'uppercase',
            }}>
              SSL Certificate Deployment
            </span>
          </div>

          {/* Body */}
          <div style={{ padding: '22px 22px 18px', position: 'relative', zIndex: 2 }}>
            {/* Progress bar */}
            {deployStatus && deployStatus.total > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ height: '4px', background: `${colors.border}44`, borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', borderRadius: '2px', transition: 'width 0.5s ease',
                    width: `${(deployStatus.completed / (onlineTotal || deployStatus.total)) * 100}%`,
                    background: barColor,
                    boxShadow: glow(barColor, 4),
                  }} />
                </div>
                <div style={{
                  fontSize: '10px', color: colors.textMuted, marginTop: '6px',
                  fontFamily: "'Electrolize', monospace", textAlign: 'right',
                }}>
                  {deployStatus.completed} / {onlineTotal} online{deployStatus.total > onlineTotal ? ` (${deployStatus.total - onlineTotal} offline)` : ''}
                </div>
              </div>
            )}

            {/* Agent list */}
            <div style={{ maxHeight: '300px', overflowY: 'auto', marginBottom: '16px' }}>
              {!deployStatus ? (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: '10px',
                  fontSize: '11px', color: colors.textMuted, fontFamily: "'Electrolize', monospace",
                }}>
                  <span style={{
                    width: '14px', height: '14px', borderRadius: '50%',
                    border: `2px solid ${colors.primary}22`, borderTopColor: colors.primary,
                    animation: 'pp-spin 0.8s linear infinite',
                  }} />
                  Updating agents and deploying certificate...
                </div>
              ) : deployStatus.agents.map(a => {
                const phase = a.phase || a.status
                const isOffline = !a.online
                const isPending = a.status === 'pending' || phase === 'pending'
                const label = a.status === 'done' ? 'CERT INSTALLED'
                  : a.status === 'failed' ? 'FAILED'
                  : phase === 'updating' ? 'UPDATING AGENT...'
                  : phase === 'waiting' ? 'AGENT UPDATED'
                  : phase === 'deploying' ? 'INSTALLING CERT...'
                  : isOffline && isPending ? 'OFFLINE — WAITING'
                  : 'PENDING'
                const dotColor = a.status === 'done' ? colors.success
                  : a.status === 'failed' ? colors.danger
                  : (phase === 'updating' || phase === 'deploying') ? colors.warn
                  : isOffline ? colors.textMuted
                  : colors.textMuted
                const isActive = phase === 'updating' || phase === 'deploying'
                return (
                  <div key={a.agent_id} style={{
                    display: 'flex', alignItems: 'center', gap: '10px',
                    padding: '6px 0', borderBottom: `1px solid ${colors.border}22`,
                    fontSize: '11px', fontFamily: "'Electrolize', monospace",
                    opacity: isOffline && isPending ? 0.5 : 1,
                  }}>
                    <span style={{
                      width: '8px', height: '8px', borderRadius: '50%', flexShrink: 0,
                      background: dotColor,
                      boxShadow: isActive ? `0 0 6px ${colors.warn}` : a.status === 'done' ? `0 0 4px ${colors.success}` : 'none',
                      animation: isActive ? 'pp-pulse 1.5s ease-in-out infinite' : 'none',
                    }} />
                    <span style={{ flex: 1, color: isOffline && isPending ? colors.textMuted : colors.text }}>
                      {a.hostname}
                      {isOffline && isPending && (
                        <span style={{ fontSize: '8px', marginLeft: '6px', color: colors.textMuted }}>●  OFFLINE</span>
                      )}
                    </span>
                    <span style={{ fontSize: '9px', letterSpacing: '0.1em', color: dotColor }}>
                      {label}
                    </span>
                  </div>
                )
              })}
            </div>

            {/* Failed output details */}
            {hasFailed && (
              <div style={{
                fontSize: '10px', color: colors.danger, fontFamily: "'Electrolize', monospace",
                padding: '8px', background: `${colors.danger}0a`, border: `1px solid ${colors.danger}22`,
                marginBottom: '12px', maxHeight: '80px', overflowY: 'auto',
              }}>
                {deployStatus!.agents.filter(a => a.status === 'failed').map(a => (
                  <div key={a.agent_id}>{a.hostname}: {a.output}</div>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          <div style={{
            padding: '14px 22px 18px',
            display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
            gap: '10px', flexWrap: 'wrap',
            position: 'relative', zIndex: 2,
            borderTop: `1px solid ${colors.border}`,
          }}>
            {isDone ? (
              <>
                {/* Status summary */}
                {deployStatus && (
                  <span style={{
                    fontSize: '10px', fontFamily: "'Electrolize', monospace",
                    color: hasFailed ? colors.warn : colors.success,
                    letterSpacing: '0.06em', marginRight: 'auto',
                  }}>
                    {deployStatus.agents.filter(a => a.status === 'done').length} installed
                    {hasFailed ? ` · ${deployStatus.agents.filter(a => a.status === 'failed').length} failed` : ''}
                  </span>
                )}
                {hasFailed && (
                  <Button variant="ghost" onClick={onRetry}>Retry Failed</Button>
                )}
                {!ssl?.enabled && ssl?.certfile && ssl?.keyfile && (
                  <Button disabled={busy} onClick={onEnableHttps}>Enable HTTPS</Button>
                )}
                <Button variant="ghost" onClick={onClose}>Close</Button>
              </>
            ) : (
              <>
                <span style={{
                  fontSize: '10px', fontFamily: "'Orbitron', sans-serif",
                  letterSpacing: '0.08em', color: colors.textMuted, marginRight: 'auto',
                }}>
                  Waiting for agents...
                </span>
                <Button variant="ghost" onClick={onClose} style={{ color: colors.danger }}>
                  Cancel
                </Button>
              </>
            )}
          </div>
        </div>
      </Animator>

      {/* Prominent warning outside modal panel */}
      {!isDone && (
        <div style={{
          marginTop: '24px',
          padding: '10px 24px',
          background: `${colors.warn}0a`,
          border: `1px solid ${colors.warn}33`,
          animation: 'pp-fadein 0.4s ease both',
          textAlign: 'center',
        }}>
          <span style={{
            fontSize: '11px', fontFamily: "'Orbitron', sans-serif",
            letterSpacing: '0.18em', textTransform: 'uppercase',
            color: colors.warn,
            textShadow: glowText(colors.warn, 4),
            fontWeight: 600,
          }}>
            ⚠ Do not leave this page while deployment is in progress
          </span>
        </div>
      )}
    </div>,
    document.body,
  )
}

function SslSection() {
  const [ssl, setSsl] = useState<{ enabled: boolean; certfile: string; keyfile: string; info: any } | null>(null)
  const [customCert, setCustomCert] = useState('')
  const [customKey, setCustomKey] = useState('')
  const [certYears, setCertYears] = useState('3')
  const [busy, setBusy] = useState(false)
  const [deployModal, setDeployModal] = useState(false)
  const [deployStatus, setDeployStatus] = useState<DeployStatus | null>(null)
  const [confirmDisable, setConfirmDisable] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const batchRef = useRef<string>('')
  const deployStartRef = useRef<number>(0)
  const { showToast } = useToast()

  const load = useCallback(async () => {
    try {
      const res = await api.sslInfo()
      setSsl(res)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { load() }, [load])

  const handleGenerate = async () => {
    setBusy(true)
    try {
      const res = await api.generateCert(parseInt(certYears))
      showToast(`Self-signed certificate generated (${certYears}y) — deploy to agents then enable HTTPS`, 'success')
      setSsl({ enabled: false, certfile: res.certfile, keyfile: res.keyfile, info: res.info })
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to generate certificate', 'error')
    } finally { setBusy(false) }
  }

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  useEffect(() => {
    if (!deployModal) return
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [deployModal])

  const pollDeployStatus = useCallback(async () => {
    if (!batchRef.current) return
    try {
      const res = await api.deploySslStatus(batchRef.current)
      setDeployStatus(res)
      // Stop polling when all ONLINE agents are done — offline ones catch up later
      const onlineCount = res.total_online ?? res.total
      const elapsed = Date.now() - deployStartRef.current
      const timedOut = elapsed > 180_000  // 3 min timeout
      if ((onlineCount > 0 && res.completed >= onlineCount) || timedOut) {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
        setBusy(false)
      }
    } catch { /* ignore */ }
  }, [])

  const handleDeploySsl = async () => {
    setBusy(true)
    setDeployStatus(null)
    batchRef.current = ''
    deployStartRef.current = Date.now()
    setDeployModal(true)
    try {
      const res = await api.deploySslToAgents()
      batchRef.current = res.batch_id
      pollDeployStatus()
      pollRef.current = setInterval(pollDeployStatus, 3000)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to deploy SSL to agents', 'error')
      setBusy(false)
      setDeployModal(false)
    }
  }

  const closeDeployModal = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    setDeployModal(false)
    setBusy(false)
  }

  const handleEnable = async (cert?: string, key?: string) => {
    const c = (cert || customCert).trim()
    const k = (key || customKey).trim()
    if (!c || !k) {
      showToast('Both certificate and key path are required', 'error')
      return
    }
    setBusy(true)
    try {
      const res = await api.sslEnable(c, k)
      showToast('SSL enabled — server restarting', 'success')
      setSsl({ enabled: true, certfile: c, keyfile: k, info: res.info })
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to enable SSL', 'error')
    } finally { setBusy(false) }
  }

  const handleEnableFromModal = async () => {
    if (!ssl?.certfile || !ssl?.keyfile) return
    setBusy(true)
    try {
      const res = await api.sslEnable(ssl.certfile, ssl.keyfile)
      showToast('SSL enabled — server restarting on HTTPS', 'success')
      setSsl({ enabled: true, certfile: ssl.certfile, keyfile: ssl.keyfile, info: res.info })
      closeDeployModal()
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to enable SSL', 'error')
    } finally { setBusy(false) }
  }

  const handleDisable = async () => {
    setBusy(true)
    try {
      await api.sslDisable()
      showToast('SSL disabled — server restarting on HTTP', 'success')
      setSsl({ enabled: false, certfile: '', keyfile: '', info: null })
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to disable SSL', 'error')
    } finally { setBusy(false) }
  }

  const statusColor = ssl?.enabled ? colors.success : colors.textMuted

  return (
    <Card style={{ marginBottom: '20px' }}>
      <SectionHeader>SSL / HTTPS</SectionHeader>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
        <span style={{
          display: 'inline-block', padding: '3px 10px', fontSize: '10px',
          letterSpacing: '0.15em', fontFamily: "'Orbitron', sans-serif",
          border: `1px solid ${statusColor}44`,
          color: statusColor,
          background: `${statusColor}0a`,
          boxShadow: ssl?.enabled ? glow(colors.success, 4) : 'none',
        }}>
          {ssl?.enabled ? 'HTTPS ACTIVE' : 'HTTP (no SSL)'}
        </span>
        {ssl?.enabled && ssl?.info && (
          <span style={{ fontSize: '10px', color: colors.textDim, fontFamily: "'Electrolize', monospace" }}>
            {ssl.info.subject} — expires {ssl.info.expires}
          </span>
        )}
      </div>

      {ssl?.enabled ? (
        <>
          <div style={{ fontSize: '11px', color: colors.textMuted, fontFamily: "'Electrolize', monospace", marginBottom: '12px', lineHeight: 1.6 }}>
            Cert: {ssl.certfile}<br />
            Key: {ssl.keyfile}
          </div>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div style={{ width: '120px' }}>
              <div style={labelStyle}>Validity</div>
              <Dropdown value={certYears} onChange={setCertYears} options={CERT_VALIDITY_OPTIONS} />
            </div>
            <Button variant="ghost" onClick={handleGenerate} disabled={busy}>
              {busy ? 'Generating...' : 'Regenerate Self-Signed'}
            </Button>
            <Button onClick={handleDeploySsl} disabled={busy}>
              {busy ? 'Deploying...' : 'Deploy Cert to Agents'}
            </Button>
            <Button variant="danger" onClick={() => setConfirmDisable(true)} disabled={busy}>
              Disable SSL
            </Button>
          </div>
        </>
      ) : (
        <>
          {/* Existing cert — enable directly or deploy first */}
          {ssl?.certfile && ssl?.keyfile && (
            <div style={{ marginBottom: '16px', padding: '12px', border: `1px solid ${colors.border}`, background: `${colors.success}06` }}>
              <div style={{ fontSize: '10px', letterSpacing: '0.15em', color: colors.textMuted, fontFamily: "'Orbitron', sans-serif", marginBottom: '8px' }}>
                CERTIFICATE AVAILABLE
              </div>
              <div style={{ fontSize: '11px', color: colors.textDim, fontFamily: "'Electrolize', monospace", marginBottom: '10px', lineHeight: 1.6 }}>
                {ssl.certfile}
                {ssl.info && <span style={{ color: colors.textMuted }}> — expires {ssl.info.expires}</span>}
              </div>
              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                <Button onClick={handleDeploySsl} disabled={busy}>
                  {busy ? 'Deploying...' : 'Deploy to Agents'}
                </Button>
                <Button onClick={() => handleEnable(ssl.certfile, ssl.keyfile)} disabled={busy}>
                  Enable HTTPS
                </Button>
              </div>
            </div>
          )}

          {/* Generate new self-signed cert */}
          <div style={{ marginBottom: '16px' }}>
            <div style={{ fontSize: '10px', letterSpacing: '0.15em', color: colors.textMuted, fontFamily: "'Orbitron', sans-serif", marginBottom: '10px' }}>
              {ssl?.certfile ? 'REGENERATE CERTIFICATE' : 'GENERATE SELF-SIGNED CERTIFICATE'}
            </div>
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div style={{ width: '120px' }}>
                <div style={labelStyle}>Validity</div>
                <Dropdown value={certYears} onChange={setCertYears} options={CERT_VALIDITY_OPTIONS} />
              </div>
              <Button variant={ssl?.certfile ? 'ghost' : undefined} onClick={handleGenerate} disabled={busy}>
                {busy ? 'Generating...' : ssl?.certfile ? 'Regenerate' : 'Generate Certificate'}
              </Button>
            </div>
          </div>

          {/* Or use own certificate */}
          <div style={{ borderTop: `1px solid ${colors.border}`, paddingTop: '14px' }}>
            <div style={{ fontSize: '10px', letterSpacing: '0.15em', color: colors.textMuted, fontFamily: "'Orbitron', sans-serif", marginBottom: '10px' }}>
              USE OWN CERTIFICATE
            </div>
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div style={{ flex: '1 1 200px' }}>
                <div style={labelStyle}>Certificate Path</div>
                <input value={customCert} onChange={e => setCustomCert(e.target.value)} placeholder="/opt/patchpilot/ssl/cert.pem" style={inputStyle} />
              </div>
              <div style={{ flex: '1 1 200px' }}>
                <div style={labelStyle}>Private Key Path</div>
                <input value={customKey} onChange={e => setCustomKey(e.target.value)} placeholder="/opt/patchpilot/ssl/key.pem" style={inputStyle} />
              </div>
              <Button onClick={() => handleEnable()} disabled={busy || !customCert.trim() || !customKey.trim()}>
                Enable SSL
              </Button>
            </div>
          </div>
        </>
      )}

      <p style={{ margin: '14px 0 0', fontSize: '10px', color: colors.textMuted, fontFamily: "'Electrolize', monospace", lineHeight: 1.6 }}>
        Enabling SSL restarts the server on HTTPS. Agents migrate automatically via canonical_url.
      </p>

      {confirmDisable && (
        <ConfirmModal
          title="Disable SSL"
          message="This will restart the server on HTTP. All agents will need to reconnect. Are you sure?"
          confirmLabel="Disable SSL"
          variant="danger"
          onConfirm={() => { setConfirmDisable(false); handleDisable() }}
          onCancel={() => setConfirmDisable(false)}
        />
      )}

      {deployModal && (
        <DeployModal
          deployStatus={deployStatus}
          ssl={ssl}
          busy={busy}
          setBusy={setBusy}
          onClose={closeDeployModal}
          onRetry={() => { closeDeployModal(); handleDeploySsl() }}
          onEnableHttps={handleEnableFromModal}
        />
      )}
    </Card>
  )
}
