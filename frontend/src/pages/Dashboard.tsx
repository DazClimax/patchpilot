import React, { useEffect, useState, useCallback, useRef, useContext } from 'react'
import { useNavigate } from 'react-router-dom'
import { Animator, Text } from '@arwes/react'
import { api, Agent } from '../api/client'
import { colors, glow, glowText, glassBg } from '../theme'
import { StatCard, SkeletonCard } from '../components/Card'
import { OnlineDot, Badge } from '../components/Badge'
import { Button } from '../components/Button'
import { ConfirmModal } from '../components/ConfirmModal'
import { SslDeployModal, type DeployStatus } from '../components/SslDeployModal'
import { PageHeader } from '../components/SectionHeader'
import { fmtAgoShort as fmtAgo, fmtUptime } from '../utils/format'
import { UserContext } from '../App'

// ─── Offline VM Alert Banner ───────────────────────────────────────────────────

function OfflineBanner({ hostnames, onDismiss }: { hostnames: string[]; onDismiss: () => void }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'flex-start',
      gap: '0',
      marginBottom: '24px',
      border: `1px solid ${colors.danger}55`,
      background: `${colors.danger}0d`,
      animation: 'pp-fadein 0.4s ease both, pp-warn-pulse 2.4s ease-in-out infinite',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Left accent bar */}
      <div style={{
        width: '4px',
        alignSelf: 'stretch',
        background: colors.danger,
        boxShadow: glow(colors.danger, 6),
        flexShrink: 0,
      }} />

      {/* Content */}
      <div style={{
        flex: 1,
        padding: '14px 16px',
        display: 'flex',
        alignItems: 'center',
        gap: '14px',
        flexWrap: 'wrap',
      }}>
        {/* Warning icon */}
        <span style={{
          fontSize: '14px',
          color: colors.danger,
          textShadow: glowText(colors.danger, 4),
          flexShrink: 0,
        }}>
          ⚠
        </span>

        {/* Label */}
        <span style={{
          fontFamily: "'Orbitron', sans-serif",
          fontSize: '10px',
          letterSpacing: '0.2em',
          textTransform: 'uppercase',
          color: colors.danger,
          textShadow: glowText(colors.danger, 3),
          flexShrink: 0,
        }}>
          Offline VMs Detected
        </span>

        {/* Hostname pills */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
          {hostnames.map(h => (
            <span key={h} style={{
              fontFamily: "'Electrolize', monospace",
              fontSize: '11px',
              letterSpacing: '0.08em',
              color: colors.danger,
              border: `1px solid ${colors.danger}44`,
              background: `${colors.danger}10`,
              padding: '2px 10px',
              textShadow: glowText(colors.danger, 2),
            }}>
              {h}
            </span>
          ))}
        </div>
      </div>

      {/* Dismiss button */}
      <button
        onClick={onDismiss}
        aria-label="Dismiss offline banner"
        style={{
          background: `${colors.danger}0d`,
          border: `1px solid ${colors.danger}33`,
          cursor: 'pointer',
          color: colors.danger,
          fontSize: '12px',
          padding: '12px 14px',
          alignSelf: 'flex-start',
          opacity: 0.7,
          lineHeight: 1,
          flexShrink: 0,
          transition: 'opacity 0.15s, box-shadow 0.15s, background 0.15s, border-color 0.15s',
          clipPath: 'polygon(4px 0%, 100% 0%, calc(100% - 4px) 100%, 0% 100%)',
        }}
        onMouseEnter={e => {
          const el = e.currentTarget as HTMLButtonElement
          el.style.opacity = '1'
          el.style.background = `${colors.danger}14`
          el.style.borderColor = `${colors.danger}66`
          el.style.boxShadow = glow(colors.danger, 6)
        }}
        onMouseLeave={e => {
          const el = e.currentTarget as HTMLButtonElement
          el.style.opacity = '0.7'
          el.style.background = `${colors.danger}0d`
          el.style.borderColor = `${colors.danger}33`
          el.style.boxShadow = 'none'
        }}
        title="Dismiss"
      >
        ✕
      </button>
    </div>
  )
}

// ─── Sort types ────────────────────────────────────────────────────────────────

type SortKey = 'status' | 'conn' | 'hostname' | 'ip' | 'os' | 'updates' | 'reboot' | 'last_job' | 'uptime' | 'last_seen'
type FilterKey = 'all' | 'online' | 'offline' | 'updates' | 'reboot' | 'outdated' | 'haos'

/** Map OS name to font-logos CSS class */
function osIcon(os: string | null): string {
  if (!os) return 'fl-tux'
  const l = os.toLowerCase()
  // Major distros
  if (l.includes('debian')) return 'fl-debian'
  if (l.includes('ubuntu')) return 'fl-ubuntu'
  if (l.includes('kubuntu')) return 'fl-kubuntu'
  if (l.includes('fedora')) return 'fl-fedora'
  if (l.includes('centos')) return 'fl-centos'
  if (l.includes('red hat') || l.includes('redhat') || l.includes('rhel')) return 'fl-redhat'
  if (l.includes('alma')) return 'fl-almalinux'
  if (l.includes('rocky')) return 'fl-rocky-linux'
  if (l.includes('opensuse') || l.includes('suse') || l.includes('tumbleweed')) return 'fl-opensuse'
  if (l.includes('alpine')) return 'fl-alpine'
  // Arch-based
  if (l.includes('manjaro')) return 'fl-manjaro'
  if (l.includes('endeavour')) return 'fl-endeavour'
  if (l.includes('garuda')) return 'fl-garuda'
  if (l.includes('artix')) return 'fl-artix'
  if (l.includes('arcolinux')) return 'fl-arcolinux'
  if (l.includes('archcraft')) return 'fl-archcraft'
  if (l.includes('arch')) return 'fl-archlinux'
  // Debian-based
  if (l.includes('mint')) return 'fl-linuxmint'
  if (l.includes('pop!_os') || l.includes('pop os') || l.includes('pop_os')) return 'fl-pop-os'
  if (l.includes('elementary')) return 'fl-elementary'
  if (l.includes('zorin')) return 'fl-zorin'
  if (l.includes('mx linux') || l.includes('mxlinux')) return 'fl-mxlinux'
  if (l.includes('kali')) return 'fl-kali-linux'
  if (l.includes('parrot')) return 'fl-parrot'
  if (l.includes('devuan')) return 'fl-devuan'
  if (l.includes('deepin')) return 'fl-deepin'
  if (l.includes('tails')) return 'fl-tails'
  if (l.includes('puppy')) return 'fl-puppy'
  // Independent
  if (l.includes('gentoo')) return 'fl-gentoo'
  if (l.includes('nixos')) return 'fl-nixos'
  if (l.includes('void')) return 'fl-void'
  if (l.includes('solus')) return 'fl-solus'
  if (l.includes('slackware')) return 'fl-slackware'
  if (l.includes('mageia')) return 'fl-mageia'
  if (l.includes('nobara')) return 'fl-nobara'
  if (l.includes('qubes')) return 'fl-qubesos'
  // BSD
  if (l.includes('freebsd')) return 'fl-freebsd'
  if (l.includes('openbsd')) return 'fl-openbsd'
  // Hardware / special
  if (l.includes('raspb') || l.includes('raspberry')) return 'fl-raspberry-pi'
  if (l.includes('coreos')) return 'fl-coreos'
  // Fallback
  return 'fl-tux'
}
type SortDir = 'asc' | 'desc'

function sortAgents(agents: Agent[], key: SortKey, dir: SortDir): Agent[] {
  const sorted = [...agents].sort((a, b) => {
    let cmp = 0
    if (key === 'status') {
      const ao = (a.seconds_ago ?? 9999) < 120 ? 0 : 1
      const bo = (b.seconds_ago ?? 9999) < 120 ? 0 : 1
      cmp = ao - bo
    } else if (key === 'hostname') {
      cmp = (a.hostname ?? '').localeCompare(b.hostname ?? '')
    } else if (key === 'ip') {
      // Sort IPs numerically by converting each octet
      const toNum = (ip: string | null) => (ip ?? '').split('.').reduce((acc, o) => acc * 256 + (parseInt(o) || 0), 0)
      cmp = toNum(a.ip) - toNum(b.ip)
    } else if (key === 'conn') {
      cmp = (a.protocol ?? '').localeCompare(b.protocol ?? '')
    } else if (key === 'os') {
      cmp = (a.os_pretty ?? '').localeCompare(b.os_pretty ?? '')
    } else if (key === 'updates') {
      cmp = (a.pending_count ?? 0) - (b.pending_count ?? 0)
    } else if (key === 'reboot') {
      cmp = (a.reboot_required ?? 0) - (b.reboot_required ?? 0)
    } else if (key === 'last_job') {
      // Sort by status (failed first), then by finished time
      const statusOrder = (s: string | null) => s === 'failed' ? 0 : s === 'done' ? 1 : 2
      cmp = statusOrder(a.last_job_status) - statusOrder(b.last_job_status)
      if (cmp === 0) cmp = (a.last_job_finished ?? '').localeCompare(b.last_job_finished ?? '')
    } else if (key === 'uptime') {
      cmp = (a.uptime_seconds ?? -1) - (b.uptime_seconds ?? -1)
    } else if (key === 'last_seen') {
      cmp = (a.seconds_ago ?? 9999) - (b.seconds_ago ?? 9999)
    }
    return dir === 'asc' ? cmp : -cmp
  })
  return sorted
}

// ─── Sortable column header ────────────────────────────────────────────────────

function SortTh({
  label,
  sortKey,
  activeKey,
  dir,
  onSort,
  align = 'left',
  className,
}: {
  label: string
  sortKey: SortKey
  activeKey: SortKey | null
  dir: SortDir
  onSort: (k: SortKey) => void
  align?: 'left' | 'center' | 'right'
  className?: string
}) {
  const active = activeKey === sortKey
  const [hover, setHover] = useState(false)

  return (
    <th
      className={className}
      onClick={() => onSort(sortKey)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      tabIndex={0}
      aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSort(sortKey) } }}
      style={{
        padding: '10px 16px',
        textAlign: align,
        fontSize: '10px',
        letterSpacing: '0.2em',
        textTransform: 'uppercase',
        color: active ? colors.primary : hover ? colors.text : colors.textMuted,
        fontWeight: 500,
        fontFamily: "'Orbitron', sans-serif",
        whiteSpace: 'nowrap',
        cursor: 'pointer',
        userSelect: 'none',
        textShadow: active ? glowText(colors.primary, 3) : 'none',
        transition: 'color 0.15s',
      }}
    >
      {label}
      {active && (
        <span style={{ marginLeft: '5px', fontSize: '8px', opacity: 0.9 }}>
          {dir === 'asc' ? '▲' : '▼'}
        </span>
      )}
      {!active && hover && (
        <span style={{ marginLeft: '5px', fontSize: '8px', opacity: 0.35 }}>▲</span>
      )}
    </th>
  )
}

// ─── Table row ────────────────────────────────────────────────────────────────

function AgentRow({
  agent,
  onClick,
  index,
  onTagsChange,
}: {
  agent: Agent
  onClick: () => void
  index: number
  onTagsChange: (id: string, tags: string) => void
}) {
  const online = (agent.seconds_ago ?? 9999) < 120
  const [hover, setHover] = useState(false)
  const [editingTags, setEditingTags] = useState(false)
  const [tagInput, setTagInput] = useState(agent.tags ?? '')
  const inputRef = useRef<HTMLInputElement>(null)

  // Keep local input in sync when agent data refreshes (and we're not editing)
  useEffect(() => {
    if (!editingTags) setTagInput(agent.tags ?? '')
  }, [agent.tags, editingTags])

  const openTagEditor = (e: React.MouseEvent) => {
    e.stopPropagation()
    setTagInput(agent.tags ?? '')
    setEditingTags(true)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  const commitTags = async (e?: React.FocusEvent | React.KeyboardEvent) => {
    if (e && 'key' in e && e.key === 'Escape') {
      setTagInput(agent.tags ?? '')
      setEditingTags(false)
      return
    }
    if (e && 'key' in e && e.key !== 'Enter') return
    setEditingTags(false)
    if (tagInput !== (agent.tags ?? '')) {
      onTagsChange(agent.id, tagInput)
    }
  }

  const tagList = (agent.tags ?? '').split(',').map(t => t.trim()).filter(Boolean)
  const jobInProgress = agent.last_job_status === 'pending' || agent.last_job_status === 'running'
  const jobInProgressLabel = agent.last_job_type
    ? `${agent.last_job_type.replace(/_/g, ' ')} in progress…`
    : 'Job in progress…'

  return (
    <tr
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        cursor: 'pointer',
        background: hover
          ? `linear-gradient(90deg, ${colors.primary}12 0%, ${colors.primary}06 60%, transparent 100%)`
          : 'transparent',
        borderBottom: `1px solid ${colors.border}`,
        transition: 'background 0.15s ease',
        animation: `pp-fadein 0.3s ease both`,
        animationDelay: `${index * 0.04}s`,
      }}
    >
      <td style={{ padding: '12px 16px' }}>
        <OnlineDot online={online} />
      </td>
      <td className="pp-hide-mobile" style={{ padding: '12px 10px', textAlign: 'center' }}>
        <span title={agent.protocol === 'https' ? 'Connected via HTTPS' : 'Connected via HTTP'} style={{
          fontSize: '9px', letterSpacing: '0.1em',
          padding: '1px 5px',
          border: `1px solid ${!online ? colors.border : agent.protocol === 'https' ? colors.success : colors.textMuted}44`,
          color: !online ? colors.textMuted : agent.protocol === 'https' ? colors.success : colors.textMuted,
          opacity: !online ? 0.55 : 1,
          fontFamily: "'Orbitron', sans-serif",
        }}>
          {agent.protocol === 'https' ? 'TLS' : 'HTTP'}
        </span>
      </td>
      <td style={{ padding: '12px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{
              color: hover ? colors.primary : colors.text,
              fontFamily: "'Orbitron', sans-serif",
              fontSize: '13px',
              textShadow: hover ? glowText(colors.primary, 4) : 'none',
              transition: 'all 0.15s',
              letterSpacing: '0.04em',
            }}>
              {agent.hostname}
            </span>
            <span style={{
              color: agent.agent_version ? colors.textMuted : colors.warn,
              fontSize: '10px',
              fontFamily: "'Electrolize', monospace",
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
            }}>
              Agent {agent.agent_version || 'unknown'}
            </span>
          </div>
          {/* Tag chips + editor — hidden on mobile */}
          {!editingTags && tagList.map(tag => (
            <Badge key={tag} color={colors.primaryDim} className="pp-hide-mobile" style={{ fontSize: '10px', padding: '1px 6px' }}>
              {tag}
            </Badge>
          ))}
          {editingTags ? (
            <input
              className="pp-hide-mobile"
              ref={inputRef}
              value={tagInput}
              onChange={e => setTagInput(e.target.value)}
              onBlur={e => commitTags(e as React.FocusEvent)}
              onKeyDown={e => commitTags(e as React.KeyboardEvent)}
              onClick={e => e.stopPropagation()}
              placeholder="prod,web,…"
              style={{
                background: `${colors.bg}cc`,
                border: `1px solid ${colors.primary}66`,
                color: colors.text,
                fontSize: '11px',
                fontFamily: "'Electrolize', monospace",
                padding: '2px 8px',
                outline: 'none',
                width: '140px',
                boxShadow: `0 0 6px ${colors.primary}33`,
              }}
            />
          ) : (
            <span
              className="pp-hide-mobile"
              title="Edit tags"
              onClick={openTagEditor}
              style={{
                cursor: 'pointer',
                color: colors.textMuted,
                fontSize: '11px',
                lineHeight: 1,
                opacity: hover ? 0.7 : 0,
                transition: 'opacity 0.15s',
                userSelect: 'none',
              }}
            >
              ✎
            </span>
          )}
        </div>
      </td>
      <td className="pp-hide-mobile" style={{ padding: '12px 16px', color: colors.textDim, fontFamily: 'monospace', fontSize: '12px' }}>
        {agent.ip ?? '—'}
      </td>
      <td className="pp-hide-mobile" style={{ padding: '12px 16px', color: colors.textDim, fontSize: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span className={osIcon(agent.os_pretty)} style={{ fontSize: '14px', color: colors.textMuted, flexShrink: 0 }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span>{agent.os_pretty ?? '—'}</span>
            <span style={{
              fontSize: '10px',
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              color: colors.textMuted,
              fontFamily: "'Electrolize', monospace",
            }}>
              {agent.agent_type === 'haos'
                ? 'Home Assistant OS'
                : agent.package_manager
                  ? `${agent.package_manager} packages`
                  : 'Package manager unknown'}
            </span>
          </div>
        </div>
      </td>
      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
        {jobInProgress ? (
          <span style={{
            display: 'inline-block',
            width: '14px', height: '14px',
            border: `2px solid ${colors.warn}44`,
            borderTopColor: colors.warn,
            borderRadius: '50%',
            animation: 'pp-spin 0.8s linear infinite',
          }} title={jobInProgressLabel} />
        ) : (agent.pending_count ?? 0) > 0 ? (
          <Badge color={colors.warn}>{agent.pending_count}</Badge>
        ) : agent.config_review_required ? (
          <span
            title="Config changes need manual review"
            style={{ color: colors.warn, fontSize: '15px', textShadow: glow(colors.warn, 4) }}
          >
            !
          </span>
        ) : (
          <span style={{ color: colors.success, fontSize: '13px', textShadow: glow(colors.success, 3) }}>✓</span>
        )}
      </td>
      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
        {agent.reboot_required ? (
          <Badge color={colors.danger}>Reboot</Badge>
        ) : (
          <span style={{ color: colors.textMuted, fontSize: '12px' }}>—</span>
        )}
      </td>
      <td className="pp-hide-mobile" style={{ padding: '12px 16px', textAlign: 'center' }}>
        {agent.last_job_status ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px' }}>
            <span
              style={{
                fontSize: '10px',
                fontFamily: "'Electrolize', monospace",
                letterSpacing: '0.06em',
                padding: '2px 8px',
                border: `1px solid ${agent.last_job_status === 'failed' ? colors.danger : colors.success}44`,
                background: `${agent.last_job_status === 'failed' ? colors.danger : colors.success}10`,
                color: agent.last_job_status === 'failed' ? colors.danger : colors.success,
                textShadow: glowText(agent.last_job_status === 'failed' ? colors.danger : colors.success, 2),
              }}
            >
              {agent.last_job_type} {agent.last_job_status === 'failed' ? '✗' : '✓'}
            </span>
            <span style={{ fontSize: '10px', color: colors.textMuted, fontFamily: 'monospace' }}>
              {agent.last_job_finished?.replace('T', ' ').slice(0, 16) ?? ''}
            </span>
          </div>
        ) : (
          <span style={{ color: colors.textMuted, fontSize: '12px' }}>—</span>
        )}
      </td>
      <td className="pp-hide-mobile" style={{ padding: '12px 16px', textAlign: 'right', color: colors.textMuted, fontSize: '11px', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
        {fmtUptime(agent.uptime_seconds)}
      </td>
      <td className="pp-hide-mobile" style={{ padding: '12px 16px', textAlign: 'right', color: colors.textMuted, fontSize: '11px', fontFamily: 'monospace' }}>
        {fmtAgo(agent.seconds_ago)}
      </td>
    </tr>
  )
}

// ─── Skeleton table rows ──────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <tr style={{ borderBottom: `1px solid ${colors.border}` }}>
      {[80, 40, 130, 90, 160, 50, 60, 65, 55, 40].map((w, i) => (
        <td key={i} style={{ padding: '12px 16px' }}>
          <div style={{
            height: '12px',
            width: w,
            maxWidth: '100%',
            background: `linear-gradient(
              90deg,
              ${colors.border} 0%,
              ${colors.primary}18 50%,
              ${colors.border} 100%
            )`,
            backgroundSize: '400px 100%',
            animation: 'pp-shimmer 1.8s linear infinite',
            animationDelay: `${i * 0.06}s`,
          }} />
        </td>
      ))}
    </tr>
  )
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <tr>
      <td colSpan={10}>
        <div style={{
          padding: '56px 32px',
          textAlign: 'center',
          animation: 'pp-fadein 0.5s ease both',
        }}>
          {/* Icon */}
          <div style={{
            fontSize: '28px',
            color: colors.textMuted,
            marginBottom: '14px',
            opacity: 0.5,
          }}>
            ⬡
          </div>
          <div style={{
            fontSize: '12px',
            color: colors.textMuted,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            fontFamily: "'Orbitron', sans-serif",
            marginBottom: '10px',
          }}>
            No VMs Registered
          </div>
          <div style={{
            fontSize: '11px',
            color: colors.textMuted,
            letterSpacing: '0.06em',
            fontFamily: "'Electrolize', monospace",
            opacity: 0.6,
          }}>
            Install the PatchPilot agent on your Linux VMs to get started
          </div>
        </div>
      </td>
    </tr>
  )
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

export function Dashboard() {
  const navigate = useNavigate()
  const { role } = useContext(UserContext)
  const canAct = role === 'admin' || role === 'user'
  const isAdmin = role === 'admin'
  const [data, setData] = useState<Awaited<ReturnType<typeof api.dashboard>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
  const [bannerDismissed, setBannerDismissed] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [filterKey, setFilterKey] = useState<FilterKey>('all')
  const [search, setSearch] = useState('')
  const [confirm, setConfirm] = useState<{ title: string; message: string; onConfirm: () => void } | null>(null)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [agentUpdateBusy, setAgentUpdateBusy] = useState(false)
  const [agentUpdateModal, setAgentUpdateModal] = useState(false)
  const [agentUpdateStatus, setAgentUpdateStatus] = useState<DeployStatus | null>(null)
  const agentUpdatePollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const agentUpdateBatchRef = useRef('')
  const agentUpdateStartRef = useRef(0)

  const load = useCallback(async () => {
    try {
      const d = await api.dashboard()
      setData(d)
      setFetchError(false)
    } catch (e) {
      console.error(e)
      setData(null)
      setFetchError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [load])

  useEffect(() => {
    return () => {
      if (agentUpdatePollRef.current) clearInterval(agentUpdatePollRef.current)
    }
  }, [])

  useEffect(() => {
    if (!agentUpdateModal) return
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [agentUpdateModal])

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const handleTagsChange = useCallback(async (id: string, tags: string) => {
    try {
      await api.setTags(id, tags)
      // Optimistically update local state so the UI reflects the change
      // before the next poll fires.
      setData(prev => {
        if (!prev) return prev
        return {
          ...prev,
          agents: prev.agents.map(a => a.id === id ? { ...a, tags } : a),
        }
      })
    } catch (e) {
      console.error('Failed to update tags', e)
    }
  }, [])

  const patchableAgents = (data?.agents ?? []).filter(
    a => a.agent_type !== 'haos' && (a.seconds_ago ?? 9999) < 120 && (a.pending_count ?? 0) > 0
  )

  const patchAll = async () => {
    setBulkBusy(true)
    try {
      await Promise.allSettled(patchableAgents.map(a => api.createJob(a.id, 'patch')))
      load()
    } catch (e) {
      console.error(e)
    } finally {
      setBulkBusy(false)
    }
  }

  const pollAgentUpdateStatus = useCallback(async () => {
    if (!agentUpdateBatchRef.current) return
    try {
      const res = await api.updateAgentsBatchStatus(agentUpdateBatchRef.current)
      setAgentUpdateStatus(res)
      const onlineCount = res.total_online ?? res.total
      const elapsed = Date.now() - agentUpdateStartRef.current
      const timedOut = elapsed > 180_000
      if ((onlineCount > 0 && res.completed >= onlineCount) || timedOut) {
        if (agentUpdatePollRef.current) {
          clearInterval(agentUpdatePollRef.current)
          agentUpdatePollRef.current = null
        }
        setAgentUpdateBusy(false)
        load()
      }
    } catch (e) {
      console.error(e)
    }
  }, [load])

  const closeAgentUpdateModal = useCallback(() => {
    if (agentUpdatePollRef.current) {
      clearInterval(agentUpdatePollRef.current)
      agentUpdatePollRef.current = null
    }
    setAgentUpdateModal(false)
    setAgentUpdateBusy(false)
  }, [])

  const stats = data?.stats
  const agents = data?.agents ?? []
  const agentTargetVersion = data?.agent_target_version ?? '1.0'
  const haAgentTargetVersion = data?.ha_agent_target_version ?? agentTargetVersion
  const onlineAgents = agents.filter(a => (a.seconds_ago ?? 9999) < 120)
  const haAutoUpdateCap = 'ha_agent_auto_update'
  const capabilityListFor = (agent: Agent) => (agent.capabilities ?? '').split(',').map(item => item.trim()).filter(Boolean)
  const hasHaAutoUpdateEnabled = (agent: Agent) => capabilityListFor(agent).includes(haAutoUpdateCap)
  const targetVersionForAgent = (agent: Agent) => agent.agent_type === 'haos' ? haAgentTargetVersion : agentTargetVersion
  const isManagedByAgentUpdate = (agent: Agent) => agent.agent_type !== 'haos' || hasHaAutoUpdateEnabled(agent)
  const updatableOnlineAgents = onlineAgents.filter(
    a => {
      if (!isManagedByAgentUpdate(a)) return false
      if ((a.agent_version?.trim() || '') === targetVersionForAgent(a)) return false
      return true
    }
  )
  const manualHaUpdateAgents = onlineAgents.filter(a => {
    if (a.agent_type !== 'haos') return false
    if ((a.agent_version?.trim() || '') === targetVersionForAgent(a)) return false
    return !hasHaAutoUpdateEnabled(a)
  })
  const updateAllAgents = useCallback(async (retryBatch?: string) => {
    setAgentUpdateBusy(true)
    setAgentUpdateStatus(null)
    agentUpdateBatchRef.current = ''
    agentUpdateStartRef.current = Date.now()
    setAgentUpdateModal(true)
    try {
      const res = await api.updateAgentsBatch(
        retryBatch,
        retryBatch ? undefined : updatableOnlineAgents.map(agent => agent.id)
      )
      agentUpdateBatchRef.current = res.batch_id
      pollAgentUpdateStatus()
      agentUpdatePollRef.current = setInterval(pollAgentUpdateStatus, 3000)
    } catch (e) {
      console.error(e)
      setAgentUpdateBusy(false)
      setAgentUpdateModal(false)
    }
  }, [pollAgentUpdateStatus, updatableOnlineAgents])
  const managedOnlineAgents = onlineAgents.filter(isManagedByAgentUpdate)
  const onlineCurrentVersionCount = managedOnlineAgents.filter(a => a.agent_version?.trim() === targetVersionForAgent(a)).length
  const onlineUnknownVersionCount = onlineAgents.filter(a => !a.agent_version?.trim()).length
  const versionCardValue = managedOnlineAgents.length === 0 ? '—' : `${onlineCurrentVersionCount}`
  const versionCardSub = managedOnlineAgents.length === 0 ? undefined : `/${managedOnlineAgents.length}`
  const versionCardMeta = `v ${agentTargetVersion}${haAgentTargetVersion !== agentTargetVersion ? ` / HA ${haAgentTargetVersion}` : ''}${manualHaUpdateAgents.length > 0 ? ` · ${manualHaUpdateAgents.length} HA manual` : ''}`
  const versionCardAccent = managedOnlineAgents.length === 0
    ? colors.textMuted
    : onlineCurrentVersionCount === managedOnlineAgents.length
      ? colors.success
      : colors.warn

  // Offline VMs (seconds_ago > 120)
  const offlineAgents = agents.filter(a => (a.seconds_ago ?? 9999) > 120)
  const showBanner = !bannerDismissed && offlineAgents.length > 0 && !loading
  const normalizedSearch = search.trim().toLowerCase()
  const filteredAgents = agents.filter(agent => {
    const matchesFilter =
      filterKey === 'all' ? true :
      filterKey === 'online' ? (agent.seconds_ago ?? 9999) < 120 :
      filterKey === 'offline' ? (agent.seconds_ago ?? 9999) >= 120 :
      filterKey === 'updates' ? (agent.pending_count ?? 0) > 0 :
      filterKey === 'reboot' ? !!agent.reboot_required :
      filterKey === 'outdated' ? isManagedByAgentUpdate(agent) && (agent.agent_version?.trim() || '') !== targetVersionForAgent(agent) :
      filterKey === 'haos' ? agent.agent_type === 'haos' :
      true
    if (!matchesFilter) return false
    if (!normalizedSearch) return true
    const haystack = [
      agent.hostname,
      agent.id,
      agent.ip,
      agent.os_pretty,
      agent.tags,
      agent.agent_version,
    ].join(' ').toLowerCase()
    return haystack.includes(normalizedSearch)
  })

  // Apply sort if active
  const displayAgents = sortKey
    ? sortAgents(filteredAgents, sortKey, sortDir)
    : filteredAgents

  return (
    <div style={{ padding: 'clamp(16px, 4vw, 32px)', maxWidth: '1400px', animation: 'pp-fadein 0.4s ease both' }}>
      {agentUpdateModal && (
        <SslDeployModal
          deployStatus={agentUpdateStatus}
          busy={agentUpdateBusy}
          hideOfflinePending
          title="Agent Update Deployment"
          inProgressText="Updating agents..."
          doneLabel="AGENT UPDATED"
          activePhaseLabel="UPDATING AGENT..."
          waitingLabel="PENDING"
          summaryVerb="updated"
          onClose={closeAgentUpdateModal}
          onRetry={() => {
            const batch = agentUpdateBatchRef.current
            closeAgentUpdateModal()
            updateAllAgents(batch)
          }}
        />
      )}
      <PageHeader right={
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {isAdmin && (
            <Button
              variant={updatableOnlineAgents.length > 0 ? 'primary' : 'ghost'}
              size="sm"
              disabled={agentUpdateBusy || updatableOnlineAgents.length === 0}
              onClick={() => setConfirm({
                title: 'Update All Agents',
                message: `Update the PatchPilot agent on ${updatableOnlineAgents.length} online VM${updatableOnlineAgents.length === 1 ? '' : 's'}?${manualHaUpdateAgents.length > 0 ? ` ${manualHaUpdateAgents.length} Home Assistant instance${manualHaUpdateAgents.length === 1 ? ' is' : 's are'} still configured for manual updates in Home Assistant.` : ''}`,
                onConfirm: () => { setConfirm(null); updateAllAgents() },
              })}
            >
              {agentUpdateBusy ? '⟳ Updating Agents…' : `⇪ Update Agents (${updatableOnlineAgents.length})`}
            </Button>
          )}
          {canAct && <Button
            variant={patchableAgents.length > 0 ? 'primary' : 'ghost'}
            size="sm"
            disabled={bulkBusy || patchableAgents.length === 0}
            onClick={() => setConfirm({
              title: 'Update All VMs',
              message: `Install pending updates on ${patchableAgents.length} VM${patchableAgents.length === 1 ? '' : 's'}? This runs the system package upgrade on each.`,
              onConfirm: () => { setConfirm(null); patchAll() },
            })}
          >
            {bulkBusy ? '⟳ Updating…' : `⟳ Update All (${patchableAgents.length})`}
          </Button>}
          {loading && (
            <span style={{
              width: '8px', height: '8px', borderRadius: '50%',
              border: `1.5px solid ${colors.primary}44`,
              borderTopColor: colors.primary,
              display: 'inline-block',
              animation: 'pp-spin 0.8s linear infinite',
            }} />
          )}
          <span style={{
            fontSize: '10px',
            color: colors.textMuted,
            letterSpacing: '0.14em',
            fontFamily: "'Electrolize', monospace",
          }}>
            AUTO-REFRESH 30s
          </span>
        </div>
      }>
        System Dashboard
      </PageHeader>

      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '16px', marginBottom: '32px' }}>
        {loading ? (
          <>
            <SkeletonCard height={90} />
            <SkeletonCard height={90} />
            <SkeletonCard height={90} />
          </>
        ) : (
          <>
            <StatCard
              label="VMs Online"
              value={stats?.online ?? 0}
              sub={`/ ${stats?.total ?? 0}`}
              accent={colors.success}
            />
            <StatCard
              label="Pending Updates"
              value={stats?.total_pending ?? 0}
              accent={(stats?.total_pending ?? 0) > 0 ? colors.warn : colors.success}
            />
            <StatCard
              label="Reboot Required"
              value={stats?.reboot_needed ?? 0}
              accent={(stats?.reboot_needed ?? 0) > 0 ? colors.danger : colors.success}
            />
            <StatCard
              label={versionCardMeta ? `Agent ${versionCardMeta}` : 'Agent'}
              value={versionCardValue}
              sub={versionCardSub}
              accent={versionCardAccent}
            />
          </>
        )}
      </div>

      {/* Offline VM alert banner */}
      {showBanner && (
        <OfflineBanner
          hostnames={offlineAgents.map(a => a.hostname)}
          onDismiss={() => setBannerDismissed(true)}
        />
      )}

      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '12px',
        flexWrap: 'wrap',
        marginBottom: '16px',
      }}>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {[
            ['all', 'All'],
            ['online', 'Online'],
            ['offline', 'Offline'],
            ['updates', 'Updates'],
            ['reboot', 'Reboot'],
            ['outdated', 'Outdated'],
            ['haos', 'HAOS'],
          ].map(([key, label]) => (
            <Button
              key={key}
              size="sm"
              variant={filterKey === key ? 'primary' : 'ghost'}
              onClick={() => setFilterKey(key as FilterKey)}
            >
              {label}
            </Button>
          ))}
        </div>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search hostname, IP, tags..."
          style={{
            minWidth: '260px',
            maxWidth: '100%',
            background: `${colors.bg}cc`,
            border: `1px solid ${colors.border}`,
            color: colors.text,
            fontSize: '12px',
            fontFamily: "'Electrolize', monospace",
            padding: '8px 12px',
            outline: 'none',
          }}
        />
      </div>

      {/* Agent table */}
      <div style={{
        border: `1px solid ${colors.border}`,
        background: glassBg(0.65),
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        position: 'relative',
      }}>
        {/* Table header */}
        <div style={{
          padding: '14px 18px',
          borderBottom: `1px solid ${colors.border}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: `linear-gradient(90deg, ${colors.primary}06 0%, transparent 60%)`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {/* Accent bar */}
            <div style={{
              width: '2px',
              height: '14px',
              background: colors.primary,
              boxShadow: glow(colors.primary, 4),
            }} />
            <span style={{
              fontFamily: "'Orbitron', sans-serif",
              fontSize: '11px',
              letterSpacing: '0.24em',
              textTransform: 'uppercase',
              color: colors.primary,
              textShadow: glowText(colors.primary, 3),
            }}>
              Registered VMs
            </span>
            {agents.length > 0 && (
              <span style={{
                fontSize: '10px',
                color: colors.textMuted,
                fontFamily: 'monospace',
                background: `${colors.primary}0d`,
                border: `1px solid ${colors.border}`,
                padding: '1px 7px',
              }}>
                {displayAgents.length}/{agents.length}
              </span>
            )}
          </div>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${colors.border}` }}>
                <SortTh
                  label="Status"
                  sortKey="status"
                  activeKey={sortKey}
                  dir={sortDir}
                  onSort={handleSort}
                  align="left"
                />
                <SortTh label="Conn" sortKey="conn" activeKey={sortKey} dir={sortDir} onSort={handleSort} align="center" className="pp-hide-mobile" />
                <SortTh
                  label="Hostname"
                  sortKey="hostname"
                  activeKey={sortKey}
                  dir={sortDir}
                  onSort={handleSort}
                  align="left"
                />
                <SortTh label="IP"     sortKey="ip"     activeKey={sortKey} dir={sortDir} onSort={handleSort} className="pp-hide-mobile" />
                <SortTh label="OS"     sortKey="os"     activeKey={sortKey} dir={sortDir} onSort={handleSort} className="pp-hide-mobile" />
                <SortTh label="Updates" sortKey="updates" activeKey={sortKey} dir={sortDir} onSort={handleSort} align="center" />
                <SortTh label="Reboot"  sortKey="reboot"  activeKey={sortKey} dir={sortDir} onSort={handleSort} align="center" />
                <SortTh label="Last Job" sortKey="last_job" activeKey={sortKey} dir={sortDir} onSort={handleSort} align="center" className="pp-hide-mobile" />
                <SortTh label="Uptime"  sortKey="uptime"  activeKey={sortKey} dir={sortDir} onSort={handleSort} align="right" className="pp-hide-mobile" />
                <SortTh label="Last Seen" sortKey="last_seen" activeKey={sortKey} dir={sortDir} onSort={handleSort} align="right" className="pp-hide-mobile" />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <>
                  <SkeletonRow />
                  <SkeletonRow />
                  <SkeletonRow />
                </>
              ) : fetchError ? (
                <tr><td colSpan={10}>
                  <div style={{ padding: '40px 32px', textAlign: 'center', color: colors.danger, fontSize: '12px', fontFamily: "'Electrolize', monospace" }}>
                    ⚠ Failed to load dashboard — check server connection
                  </div>
                </td></tr>
              ) : displayAgents.length === 0 ? (
                <EmptyState />
              ) : (
                displayAgents.map((a, i) => (
                  <AgentRow
                    key={a.id}
                    agent={a}
                    index={i}
                    onClick={() => navigate(`/vm/${a.id}`)}
                    onTagsChange={handleTagsChange}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {confirm && (
        <ConfirmModal
          title={confirm.title}
          message={confirm.message}
          onConfirm={confirm.onConfirm}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  )
}
