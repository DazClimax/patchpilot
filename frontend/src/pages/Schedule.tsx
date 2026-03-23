import React, { useEffect, useState, useCallback, useRef, useContext } from 'react'
import { api, Schedule } from '../api/client'
import { colors, glow, glowText, glowInset, glassBg } from '../theme'
import { Card } from '../components/Card'
import { Badge } from '../components/Badge'
import { Button } from '../components/Button'
import { PageHeader, SectionHeader } from '../components/SectionHeader'
import { Dropdown } from '../components/Dropdown'
import { useToast } from '../components/Toast'
import { ConfirmModal } from '../components/ConfirmModal'
import { UserContext } from '../App'
import { describeCron } from '../utils/format'

const CRON_PRESETS = [
  { label: 'Daily 02:00',       value: '0 2 * * *'   },
  { label: 'Daily 04:00',       value: '0 4 * * *'   },
  { label: 'Sundays 03:00',     value: '0 3 * * 0'   },
  { label: 'Mondays 05:00',     value: '0 5 * * 1'   },
  { label: 'Every 6 hours',     value: '0 */6 * * *' },
]

interface FormState {
  name: string
  cron: string
  action: string
  target: string
}

// ─── Multi-VM picker ──────────────────────────────────────────────────────────

/** Converts between the string target stored in DB and a Set of selected IDs.
 *  "all" → empty Set  |  "vm1,vm2" → Set{"vm1","vm2"} */
function targetToSet(target: string): Set<string> {
  if (!target || target === 'all') return new Set()
  return new Set(target.split(',').map(s => s.trim()).filter(Boolean))
}
function setToTarget(ids: Set<string>): string {
  if (ids.size === 0) return 'all'
  return [...ids].join(',')
}

function VmMultiPicker({
  agents,
  value,
  onChange,
}: {
  agents: { id: string; hostname: string }[]
  value: string          // "all" | "id1,id2"
  onChange: (v: string) => void
}) {
  const selected = targetToSet(value)
  const isAll = selected.size === 0
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const toggleAll = () => { onChange('all') }

  const toggleAgent = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) {
      next.delete(id)
      // If nothing left → revert to "all"
      onChange(next.size === 0 ? 'all' : setToTarget(next))
    } else {
      next.add(id)
      onChange(setToTarget(next))
    }
  }

  // Summary label for the trigger button
  const label = isAll
    ? 'All VMs'
    : selected.size === 1
    ? agents.find(a => selected.has(a.id))?.hostname ?? [...selected][0]
    : `${selected.size} VMs selected`

  const base: React.CSSProperties = {
    width: '100%',
    padding: '9px 12px',
    background: colors.bg,
    border: `1px solid ${open ? colors.primary : colors.border}`,
    color: isAll ? colors.textDim : colors.text,
    fontFamily: "'Electrolize', monospace",
    fontSize: '13px',
    outline: 'none',
    letterSpacing: '0.05em',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    boxShadow: open ? `inset 0 0 0 1px ${colors.primary}44` : 'none',
    transition: 'border-color 0.15s, box-shadow 0.15s',
    userSelect: 'none',
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div style={base as React.CSSProperties} onClick={() => setOpen(o => !o)}>
        <span>{label}</span>
        <span style={{ fontSize: '10px', color: colors.textMuted, marginLeft: '8px' }}>
          {open ? '▲' : '▼'}
        </span>
      </div>

      {open && (
        <div style={{
          position: 'absolute',
          top: 'calc(100% + 4px)',
          left: 0,
          right: 0,
          zIndex: 100,
          background: colors.bgCard,
          border: `1px solid ${colors.primary}55`,
          boxShadow: `0 8px 24px rgba(0,0,0,0.5), 0 0 12px ${colors.primary}18`,
          animation: 'pp-fadein 0.12s ease both',
          maxHeight: '260px',
          overflowY: 'auto',
        }}>
          {/* All VMs option */}
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '10px 12px',
              cursor: 'pointer',
              borderBottom: `1px solid ${colors.border}`,
              background: isAll ? `${colors.primary}10` : 'transparent',
              transition: 'background 0.12s',
            }}
          >
            <span style={{
              width: '14px', height: '14px', flexShrink: 0,
              border: `1px solid ${isAll ? colors.primary : colors.border}`,
              background: isAll ? colors.primary : 'transparent',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '10px', color: colors.bg,
              transition: 'all 0.12s',
            }}>
              {isAll && '✓'}
            </span>
            <span
              style={{
                fontFamily: "'Electrolize', monospace",
                fontSize: '12px',
                letterSpacing: '0.08em',
                color: isAll ? colors.primary : colors.textDim,
              }}
              onClick={toggleAll}
            >
              All VMs
            </span>
          </label>

          {agents.length === 0 && (
            <div style={{ padding: '12px', fontSize: '11px', color: colors.textMuted, fontFamily: "'Electrolize', monospace" }}>
              No VMs registered
            </div>
          )}

          {agents.map(agent => {
            const checked = selected.has(agent.id)
            return (
              <label
                key={agent.id}
                onClick={() => toggleAgent(agent.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '9px 12px',
                  cursor: 'pointer',
                  background: checked ? `${colors.primary}08` : 'transparent',
                  borderBottom: `1px solid ${colors.border}22`,
                  transition: 'background 0.12s',
                }}
              >
                <span style={{
                  width: '14px', height: '14px', flexShrink: 0,
                  border: `1px solid ${checked ? colors.primary : colors.border}`,
                  background: checked ? colors.primary : 'transparent',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '10px', color: colors.bg,
                  transition: 'all 0.12s',
                }}>
                  {checked && '✓'}
                </span>
                <span style={{
                  fontFamily: "'Electrolize', monospace",
                  fontSize: '12px',
                  letterSpacing: '0.08em',
                  color: checked ? colors.text : colors.textDim,
                }}>
                  {agent.hostname}
                </span>
                <span style={{ marginLeft: 'auto', fontSize: '10px', color: colors.textMuted, fontFamily: 'monospace' }}>
                  {agent.id !== agent.hostname ? agent.id : ''}
                </span>
              </label>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─── Shared input / label styles (factory so they can ref state) ──────────────

function useInputStyle() {
  const base: React.CSSProperties = {
    width: '100%',
    padding: '9px 12px',
    background: `${colors.bg}`,
    border: `1px solid ${colors.border}`,
    color: colors.text,
    fontFamily: "'Electrolize', monospace",
    fontSize: '13px',
    outline: 'none',
    letterSpacing: '0.05em',
    transition: 'border-color 0.15s, box-shadow 0.15s',
  }
  return base
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '10px',
  letterSpacing: '0.25em',
  textTransform: 'uppercase',
  color: colors.textMuted,
  marginBottom: '6px',
  fontFamily: "'Orbitron', sans-serif",
}

function FocusInput({
  value,
  onChange,
  placeholder,
  required,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  required?: boolean
}) {
  const [focused, setFocused] = useState(false)
  const base = useInputStyle()

  return (
    <input
      style={{
        ...base,
        borderColor: focused ? colors.primary : colors.border,
        boxShadow: focused ? glowInset(colors.primary) : 'none',
      }}
      value={value}
      onChange={e => onChange(e.target.value)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      placeholder={placeholder}
      required={required}
    />
  )
}

function FocusSelect({
  value,
  onChange,
  children,
}: {
  value: string
  onChange: (v: string) => void
  children: React.ReactNode
}) {
  const [focused, setFocused] = useState(false)
  const base = useInputStyle()

  return (
    <select
      style={{
        ...base,
        cursor: 'pointer',
        borderColor: focused ? colors.primary : colors.border,
        boxShadow: focused ? glowInset(colors.primary) : 'none',
      }}
      value={value}
      onChange={e => onChange(e.target.value)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
    >
      {children}
    </select>
  )
}

// ─── Cron help panel ──────────────────────────────────────────────────────────

const CRON_FIELDS = [
  { field: 'Minute',     range: '0–59',  example: '30' },
  { field: 'Hour',       range: '0–23',  example: '4'  },
  { field: 'Day/Month',  range: '1–31',  example: '*'  },
  { field: 'Month',      range: '1–12',  example: '*'  },
  { field: 'Day/Week',   range: '0–6',   example: '1'  },
]

function CronHelp() {
  const [open, setOpen] = useState(false)

  return (
    <span style={{ position: 'relative', display: 'inline-block', marginLeft: '6px' }}>
      <span
        onClick={() => setOpen(o => !o)}
        title="Cron expression help"
        style={{
          cursor: 'pointer',
          fontSize: '11px',
          color: open ? colors.primary : colors.textMuted,
          border: `1px solid ${open ? colors.primary + '66' : colors.border}`,
          borderRadius: '50%',
          width: '16px',
          height: '16px',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          userSelect: 'none',
          transition: 'all 0.15s',
          textShadow: open ? glowText(colors.primary, 3) : 'none',
          lineHeight: 1,
        }}
      >
        ?
      </span>
      {open && (
        <div style={{
          position: 'absolute',
          top: '22px',
          left: '0',
          zIndex: 200,
          background: colors.bgCard,
          border: `1px solid ${colors.border}`,
          padding: '14px',
          minWidth: '320px',
          boxShadow: `0 4px 24px rgba(0,0,0,0.6), 0 0 12px ${colors.primary}18`,
          animation: 'pp-fadein 0.15s ease both',
        }}>
          <div style={{
            fontFamily: "'Orbitron', sans-serif",
            fontSize: '10px',
            letterSpacing: '0.2em',
            textTransform: 'uppercase',
            color: colors.primary,
            marginBottom: '10px',
          }}>
            Cron Syntax
          </div>
          {/* Field diagram */}
          <div style={{
            fontFamily: 'monospace',
            fontSize: '12px',
            color: colors.primary,
            background: `${colors.primary}0a`,
            padding: '8px 10px',
            border: `1px solid ${colors.primary}22`,
            marginBottom: '10px',
            letterSpacing: '0.1em',
          }}>
            ┌──────── minute (0-59)<br/>
            │ ┌────── hour (0-23)<br/>
            │ │ ┌──── day of month (1-31)<br/>
            │ │ │ ┌── month (1-12)<br/>
            │ │ │ │ ┌ day of week (0=Sun)<br/>
            │ │ │ │ │<br/>
            * * * * *
          </div>
          {/* Special chars */}
          <div style={{ fontSize: '10px', fontFamily: "'Electrolize', monospace", color: colors.textDim }}>
            {[
              ['*',    'every value'],
              ['*/n',  'every n-th (e.g. */6 = every 6h)'],
              ['n,m',  'specific values (e.g. 1,15)'],
              ['n-m',  'range (e.g. 9-17)'],
            ].map(([sym, desc]) => (
              <div key={sym} style={{ display: 'flex', gap: '10px', marginBottom: '3px' }}>
                <code style={{ color: colors.primary, minWidth: '40px' }}>{sym}</code>
                <span style={{ color: colors.textMuted }}>{desc}</span>
              </div>
            ))}
          </div>
          <div style={{
            marginTop: '10px',
            paddingTop: '10px',
            borderTop: `1px solid ${colors.border}`,
            fontSize: '10px',
            color: colors.textMuted,
            fontFamily: "'Electrolize', monospace",
          }}>
            All times are evaluated in <span style={{ color: colors.primary }}>server local time (CET/CEST)</span>.
          </div>
        </div>
      )}
    </span>
  )
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptySchedules() {
  return (
    <div style={{ padding: '60px 32px', textAlign: 'center', animation: 'pp-fadein 0.5s ease both' }}>
      <div style={{ fontSize: '26px', marginBottom: '14px', opacity: 0.4, color: colors.textDim }}>◷</div>
      <div style={{
        fontSize: '12px',
        color: colors.textMuted,
        letterSpacing: '0.2em',
        textTransform: 'uppercase',
        fontFamily: "'Orbitron', sans-serif",
        marginBottom: '10px',
      }}>
        No Schedules Configured
      </div>
      <div style={{
        fontSize: '11px',
        color: colors.textMuted,
        letterSpacing: '0.06em',
        fontFamily: "'Electrolize', monospace",
        opacity: 0.6,
      }}>
        Create a schedule to automate patch jobs across your VMs
      </div>
    </div>
  )
}

// ─── SchedulePage ─────────────────────────────────────────────────────────────

export function SchedulePage() {
  const { role } = useContext(UserContext)
  const isAdmin = role === 'admin'
  const canAct = role === 'admin' || role === 'user'
  const [data, setData] = useState<Awaited<ReturnType<typeof api.schedules>> | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<FormState>({ name: '', cron: '0 2 * * *', action: 'patch', target: 'all' })
  const [saving, setSaving] = useState(false)
  const [confirm, setConfirm] = useState<{ title: string; message: string; onConfirm: () => void } | null>(null)
  const [serverTime, setServerTime] = useState<string | null>(null)
  const { showToast } = useToast()
  const [serverTz, setServerTz] = useState<string>('Server')
  const timeRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    try {
      const d = await api.schedules()
      setData(d)
    } catch { /* silently fail — data stays stale */ }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const fetchTime = async () => {
      try {
        const res = await fetch('/api/server-time')
        if (res.ok) {
          const d = await res.json()
          setServerTime(d.local)
          if (d.tz) setServerTz(d.tz)
        }
      } catch { /* ignore */ }
    }
    fetchTime()
    timeRef.current = setInterval(fetchTime, 30_000)
    return () => { if (timeRef.current) clearInterval(timeRef.current) }
  }, [])

  const openNew = () => {
    setEditingId(null)
    setForm({ name: '', cron: '0 2 * * *', action: 'patch', target: 'all' })
    setShowForm(true)
  }

  const openEdit = (s: Schedule) => {
    setEditingId(s.id)
    setForm({ name: s.name, cron: s.cron, action: s.action, target: s.target })
    setShowForm(true)
  }

  const closeForm = () => {
    setShowForm(false)
    setEditingId(null)
    setForm({ name: '', cron: '0 2 * * *', action: 'patch', target: 'all' })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name || !form.cron) return
    setSaving(true)
    try {
      if (editingId !== null) {
        await api.updateSchedule(editingId, form)
      } else {
        await api.createSchedule(form)
      }
      await load()
      closeForm()
    } catch (err: any) {
      showToast(err?.message || 'Failed to save schedule', 'error')
    } finally {
      setSaving(false)
    }
  }

  const toggle = async (s: Schedule) => {
    try {
      await api.toggleSchedule(s.id, !s.enabled)
      await load()
    } catch {
      showToast('Failed to toggle schedule', 'error')
    }
  }

  const runNow = (s: Schedule) => {
    setConfirm({
      title: 'Run Now',
      message: `Immediately trigger "${s.name}"? This will queue jobs for ${s.target === 'all' ? 'all VMs' : 'the selected VMs'}.`,
      onConfirm: async () => {
        setConfirm(null)
        try {
          await api.runScheduleNow(s.id)
          showToast('Jobs queued', 'success')
          load()
        } catch {
          showToast('Failed to run schedule', 'error')
        }
      },
    })
  }

  const remove = (s: Schedule) => {
    setConfirm({
      title: 'Delete Schedule',
      message: `Delete schedule "${s.name}"? This cannot be undone.`,
      onConfirm: async () => {
        setConfirm(null)
        try {
          await api.deleteSchedule(s.id)
          await load()
        } catch {
          showToast('Failed to delete schedule', 'error')
        }
      },
    })
  }

  const schedules = data?.schedules ?? []
  const agents = data?.agents ?? []

  return (
    <div style={{ padding: 'clamp(16px, 4vw, 32px)', maxWidth: '1400px', animation: 'pp-fadein 0.4s ease both' }}>
      {confirm && (
        <ConfirmModal
          title={confirm.title}
          message={confirm.message}
          confirmLabel={confirm.title === 'Run Now' ? 'Run Now' : 'Delete'}
          variant={confirm.title === 'Run Now' ? 'primary' : 'danger'}
          onConfirm={confirm.onConfirm}
          onCancel={() => setConfirm(null)}
        />
      )}
      <PageHeader right={
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {serverTime && (
            <div style={{
              fontSize: '10px',
              fontFamily: "'Electrolize', monospace",
              color: colors.textMuted,
              letterSpacing: '0.1em',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-end',
            }}>
              <span style={{ color: colors.textMuted, fontSize: '10px', letterSpacing: '0.2em', textTransform: 'uppercase' }}>Server {serverTz}</span>
              <span style={{ color: colors.primary, fontFamily: 'monospace', fontSize: '12px', textShadow: glowText(colors.primary, 2) }}>
                {serverTime}
              </span>
            </div>
          )}
          {isAdmin && <Button
            variant={showForm ? 'ghost' : 'primary'}
            onClick={showForm ? closeForm : openNew}
          >
            {showForm ? '✕ Cancel' : '+ New Schedule'}
          </Button>}
        </div>
      }>
        Schedules
      </PageHeader>

      {/* Create / Edit form */}
      {showForm && (
        <div style={{
          marginBottom: '28px',
          animation: 'pp-fadein 0.25s ease both',
          position: 'relative',
          zIndex: 2,
        }}>
          <Card>
            <SectionHeader>{editingId !== null ? 'Edit Schedule' : 'New Schedule'}</SectionHeader>
            <form onSubmit={handleSubmit}>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: '18px',
                marginBottom: '18px',
              }}>
                {/* Name */}
                <div>
                  <label style={labelStyle}>Name</label>
                  <FocusInput
                    value={form.name}
                    onChange={v => setForm(f => ({ ...f, name: v }))}
                    placeholder="e.g. Nightly Patch"
                    required
                  />
                </div>

                {/* Action */}
                <div>
                  <label style={labelStyle}>Action</label>
                  <Dropdown
                    value={form.action}
                    onChange={v => setForm(f => ({ ...f, action: v }))}
                    options={[
                      { value: 'patch', label: 'Patch (apt upgrade)' },
                      { value: 'autoremove', label: 'Autoremove (apt autoremove)' },
                      { value: 'update_agent', label: 'Update Agent' },
                      { value: 'reboot', label: 'Reboot' },
                    ]}
                  />
                </div>

                {/* Cron expression */}
                <div>
                  <label style={{ ...labelStyle, display: 'flex', alignItems: 'center' }}>
                    Cron Expression <CronHelp />
                  </label>
                  <FocusInput
                    value={form.cron}
                    onChange={v => setForm(f => ({ ...f, cron: v }))}
                    placeholder="0 2 * * *"
                    required
                  />
                  {/* Preset chips */}
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '10px' }}>
                    {CRON_PRESETS.map(p => {
                      const active = form.cron === p.value
                      return (
                        <button
                          key={p.value}
                          type="button"
                          onClick={() => setForm(f => ({ ...f, cron: p.value }))}
                          style={{
                            padding: '3px 9px',
                            fontSize: '10px',
                            letterSpacing: '0.06em',
                            fontFamily: "'Electrolize', monospace",
                            background: active ? `${colors.primary}18` : 'transparent',
                            border: `1px solid ${active ? colors.primary : colors.border}`,
                            color: active ? colors.primary : colors.textDim,
                            cursor: 'pointer',
                            textShadow: active ? glowText(colors.primary, 3) : 'none',
                            transition: 'all 0.12s',
                          }}
                        >
                          {p.label}
                        </button>
                      )
                    })}
                  </div>
                  {/* Human-readable cron preview */}
                  {form.cron && describeCron(form.cron) && (
                    <div style={{
                      marginTop: '8px',
                      fontSize: '11px',
                      color: colors.primary,
                      fontFamily: "'Electrolize', monospace",
                      letterSpacing: '0.04em',
                    }}>
                      → {describeCron(form.cron)}
                    </div>
                  )}
                </div>

                {/* Target */}
                <div style={{ position: 'relative', zIndex: 10 }}>
                  <label style={labelStyle}>Target VMs</label>
                  <VmMultiPicker
                    agents={agents}
                    value={form.target}
                    onChange={v => setForm(f => ({ ...f, target: v }))}
                  />
                  {form.target !== 'all' && targetToSet(form.target).size > 0 && (
                    <div style={{
                      marginTop: '6px',
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: '4px',
                    }}>
                      {[...targetToSet(form.target)].map(id => {
                        const host = agents.find(a => a.id === id)?.hostname ?? id
                        return (
                          <span key={id} style={{
                            fontSize: '10px',
                            fontFamily: "'Electrolize', monospace",
                            padding: '1px 7px',
                            border: `1px solid ${colors.primary}44`,
                            background: `${colors.primary}0a`,
                            color: colors.primary,
                          }}>
                            {host}
                          </span>
                        )
                      })}
                    </div>
                  )}
                </div>
              </div>

              <Button type="submit" loading={saving} disabled={saving}>
                {saving ? 'Saving...' : editingId !== null ? 'Save Changes' : 'Create Schedule'}
              </Button>
            </form>
          </Card>
        </div>
      )}

      {/* Schedule list */}
      <SectionHeader right={
        schedules.length > 0
          ? <span style={{ fontSize: '10px', color: colors.textMuted, fontFamily: 'monospace' }}>
              {schedules.filter(s => s.enabled).length} active
            </span>
          : undefined
      }>
        Active Schedules
      </SectionHeader>

      <div style={{
        border: `1px solid ${colors.border}`,
        background: glassBg(0.65),
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        position: 'relative',
        zIndex: 1,
        overflowX: 'auto',
      }}>
        {schedules.length === 0 ? (
          <EmptySchedules />
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${colors.border}` }}>
                {['Name', 'Cron', 'Action', 'Target', 'Status', 'Last Run', 'Next Run', ''].map((h, i) => (
                  <th key={i} style={{
                    padding: '10px 16px',
                    textAlign: i === 7 ? 'right' : 'left',
                    fontSize: '10px',
                    letterSpacing: '0.2em',
                    textTransform: 'uppercase',
                    color: colors.textMuted,
                    fontWeight: 500,
                    fontFamily: "'Orbitron', sans-serif",
                    whiteSpace: 'nowrap',
                  }}>
                    {h === 'Cron' ? <span style={{ display: 'inline-flex', alignItems: 'center' }}>Cron <CronHelp /></span> : h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {schedules.map((s, idx) => {
                // Build display label for target (handles "all", single ID, or "id1,id2,id3")
                let agentName: React.ReactNode
                if (s.target === 'all') {
                  agentName = 'All VMs'
                } else {
                  const ids = s.target.split(',').map(t => t.trim()).filter(Boolean)
                  if (ids.length === 1) {
                    agentName = agents.find(a => a.id === ids[0])?.hostname ?? ids[0]
                  } else {
                    const names = ids.map(id => agents.find(a => a.id === id)?.hostname ?? id)
                    const preview = names.slice(0, 2).join(', ')
                    agentName = names.length > 2
                      ? <span title={names.join(', ')}>{preview} <span style={{ color: colors.textMuted }}>+{names.length - 2}</span></span>
                      : preview
                  }
                }
                return (
                  <tr
                    key={s.id}
                    style={{
                      borderBottom: `1px solid ${colors.border}22`,
                      animation: 'pp-fadein 0.25s ease both',
                      animationDelay: `${idx * 0.04}s`,
                    }}
                  >
                    <td style={{
                      padding: '12px 16px',
                      color: colors.text,
                      fontFamily: "'Orbitron', sans-serif",
                      fontSize: '12px',
                      letterSpacing: '0.04em',
                    }}>
                      {s.name}
                    </td>
                    <td style={{ padding: '12px 16px', whiteSpace: 'nowrap' }}>
                      <code style={{
                        color: colors.primary,
                        fontFamily: 'monospace',
                        fontSize: '12px',
                        textShadow: glowText(colors.primary, 2),
                        background: `${colors.primary}0a`,
                        padding: '2px 6px',
                        border: `1px solid ${colors.primary}22`,
                      }}>
                        {s.cron}
                      </code>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <Badge color={s.action === 'reboot' ? colors.danger : colors.primary}>
                        {s.action.toUpperCase()}
                      </Badge>
                    </td>
                    <td style={{ padding: '12px 16px', color: colors.textDim, fontSize: '12px' }}>
                      {agentName}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      {s.enabled ? (
                        <Badge color={colors.success}>Active</Badge>
                      ) : (
                        <Badge color={colors.textMuted}>Paused</Badge>
                      )}
                    </td>
                    <td style={{
                      padding: '12px 16px',
                      color: colors.textMuted,
                      fontFamily: 'monospace',
                      fontSize: '11px',
                      whiteSpace: 'nowrap',
                    }}>
                      {s.last_run ? s.last_run.replace('T', ' ').slice(0, 16) : '—'}
                    </td>
                    <td style={{
                      padding: '12px 16px',
                      color: s.next_run ? colors.primary : colors.textMuted,
                      fontFamily: 'monospace',
                      fontSize: '11px',
                      whiteSpace: 'nowrap',
                    }}>
                      {s.next_run ? s.next_run.replace('T', ' ').slice(0, 16) : '—'}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      {canAct && <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                        <Button size="sm" variant="primary" onClick={() => runNow(s)}>
                          ▶ Run
                        </Button>
                        {isAdmin && <Button size="sm" variant="ghost" onClick={() => openEdit(s)}>
                          Edit
                        </Button>}
                        {isAdmin && <Button size="sm" variant="ghost" onClick={() => toggle(s)}>
                          {s.enabled ? 'Pause' : 'Resume'}
                        </Button>}
                        {isAdmin && <Button size="sm" variant="danger" onClick={() => remove(s)}>
                          ✕
                        </Button>}
                      </div>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
