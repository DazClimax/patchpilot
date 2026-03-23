import React, { useEffect, useRef, useState, useCallback } from 'react'
import { api, Settings, auth } from '../api/client'
import { colors, glow, glowText, glassBg } from '../theme'
import { Card } from '../components/Card'
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
  server_port: '8000',
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
      const result = await api.saveSettings(form)
      if (result.restart_pending && result.new_port) {
        const newPort = result.new_port
        setRestartPort(newPort)
        setRestarting(true)
        // Pass admin key in hash so sessionStorage (per-origin) survives the
        // port change. Use no-cors so the cross-origin poll isn't CORS-blocked.
        const origin = `${window.location.protocol}//${window.location.hostname}:${newPort}`
        const redirectUrl = `${origin}/#pp-key=${encodeURIComponent(auth.getKey())}`
        const poll = setInterval(async () => {
          try {
            const ctrl = new AbortController()
            const t = setTimeout(() => ctrl.abort(), 2000)
            await fetch(`${origin}/api/ping`, { mode: 'no-cors', signal: ctrl.signal })
            clearTimeout(t)
            clearInterval(poll)
            portPollRef.current = null
            window.location.href = redirectUrl
          } catch { /* still restarting */ }
        }, 1500)
        portPollRef.current = poll
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

      <form onSubmit={handleSubmit}>

        {/* ------------------------------------------------------------------ */}
        {/* Telegram                                                             */}
        {/* ------------------------------------------------------------------ */}
        <Card style={{ marginBottom: '20px' }}>
          <SectionHeader right={
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={testing === 'telegram'}
              onClick={() => handleTest('telegram')}
            >
              {testing === 'telegram' ? 'SENDING...' : 'SEND TEST'}
            </Button>
          }>
            Telegram
          </SectionHeader>

          <TelegramGuide />

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
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
              disabled={testing === 'email'}
              onClick={() => handleTest('email')}
            >
              {testing === 'email' ? 'SENDING...' : 'SEND TEST'}
            </Button>
          }>
            E-Mail (SMTP)
          </SectionHeader>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
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
        </Card>

        {/* ------------------------------------------------------------------ */}
        {/* Event-Toggles                                                        */}
        {/* ------------------------------------------------------------------ */}
        <Card style={{ marginBottom: '24px' }}>
          <SectionHeader>Notification Events</SectionHeader>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
              <Toggle
                label="VM offline after"
                name="notify_offline"
                value={form.notify_offline}
                onChange={handleChange}
              />
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  type="number"
                  min="1"
                  max="120"
                  value={form.notify_offline_minutes}
                  onChange={e => handleChange('notify_offline_minutes', e.target.value)}
                  disabled={form.notify_offline === '0'}
                  style={{
                    width: '64px',
                    padding: '4px 8px',
                    background: colors.bg,
                    border: `1px solid ${form.notify_offline === '1' ? colors.border : colors.border + '44'}`,
                    color: form.notify_offline === '1' ? colors.text : colors.textMuted,
                    fontFamily: "'Electrolize', monospace",
                    fontSize: '13px',
                    outline: 'none',
                    textAlign: 'center',
                  }}
                />
                <span style={{ fontSize: '12px', color: colors.textMuted, fontFamily: "'Electrolize', monospace" }}>
                  minutes
                </span>
              </div>
            </div>
            <div style={divider} />
            <Toggle
              label="Updates available / Reboot required"
              name="notify_patches"
              value={form.notify_patches}
              onChange={handleChange}
            />
            <div style={divider} />
            <Toggle
              label="Patch job failed"
              name="notify_failures"
              value={form.notify_failures}
              onChange={handleChange}
            />
          </div>
        </Card>

        {/* ------------------------------------------------------------------ */}
        {/* Server                                                               */}
        {/* ------------------------------------------------------------------ */}
        <Card style={{ marginBottom: '20px' }}>
          <SectionHeader>Server</SectionHeader>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '24px', flexWrap: 'wrap' }}>
            <div style={{ width: '160px', flexShrink: 0 }}>
              <Field
                label="HTTP Port"
                name="server_port"
                value={form.server_port}
                onChange={handleChange}
                placeholder="8000"
              />
            </div>
            <p style={{
              margin: '22px 0 0',
              fontSize: '11px',
              fontFamily: "'Electrolize', monospace",
              color: colors.textMuted,
              letterSpacing: '0.04em',
              lineHeight: 1.6,
              whiteSpace: 'normal',
            }}>
              Restarts the server on the new port. Agents migrate automatically on their next heartbeat — no manual config update needed.
            </p>
          </div>
        </Card>

        {/* ------------------------------------------------------------------ */}
        {/* Save button                                                          */}
        {/* ------------------------------------------------------------------ */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Button type="submit" disabled={saving || !isDirty}>
            {saving ? 'SAVING...' : isDirty ? '● SAVE SETTINGS' : 'SAVE SETTINGS'}
          </Button>
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

      {restarting && (
        <div style={{
          position: 'fixed', inset: 0,
          background: `${colors.bg}ee`,
          backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: '20px',
          zIndex: 10000, animation: 'pp-fadein 0.3s ease both',
        }}>
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
        </div>
      )}
    </div>
  )
}
