import React, { useEffect, useState, useCallback, useContext } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api, Agent, Package, Job } from '../api/client'
import { UserContext } from '../App'
import { colors, glow, glowText, glowStrong, glassBg } from '../theme'
import { Card, SkeletonCard } from '../components/Card'
import { Badge, OnlineDot } from '../components/Badge'
import { Button } from '../components/Button'
import { PageHeader, SectionHeader } from '../components/SectionHeader'
import { LogModal } from '../components/LogModal'
import { ConfirmModal } from '../components/ConfirmModal'
import { fmtAgo, fmtUptime } from '../utils/format'

function jobStatus(s: string): [string, string] {
  const map: Record<string, [string, string]> = {
    done:    ['✓ Done',    colors.success],
    failed:  ['✗ Failed',  colors.danger],
    running: ['Running', colors.warn],
    pending: ['· Pending', colors.textDim],
  }
  return map[s] ?? [s.toUpperCase(), colors.textDim]
}

function jobTypeColor(t: string) {
  const map: Record<string, string> = {
    patch:  colors.primary,
    reboot: colors.danger,
  }
  return map[t] ?? colors.textDim
}

// ─── Loading skeleton ─────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div style={{ padding: '32px', maxWidth: '1400px', animation: 'pp-fadein 0.3s ease both' }}>
      {/* Page header skeleton */}
      <div style={{ marginBottom: '28px', paddingBottom: '18px', borderBottom: `1px solid ${colors.border}` }}>
        <div style={{ height: '22px', width: '280px', marginBottom: '8px',
          background: `linear-gradient(90deg, ${colors.border} 0%, ${colors.primary}14 50%, ${colors.border} 100%)`,
          backgroundSize: '400px 100%', animation: 'pp-shimmer 1.8s linear infinite',
        }} />
      </div>
      {/* Status row */}
      <div style={{ height: '16px', width: '160px', marginBottom: '24px',
        background: `linear-gradient(90deg, ${colors.border} 0%, ${colors.primary}14 50%, ${colors.border} 100%)`,
        backgroundSize: '400px 100%', animation: 'pp-shimmer 1.8s linear infinite',
      }} />
      {/* Info cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '24px' }}>
        <SkeletonCard height={72} />
        <SkeletonCard height={72} />
        <SkeletonCard height={72} />
        <SkeletonCard height={72} />
      </div>
      {/* Table area */}
      <SkeletonCard height={200} />
    </div>
  )
}

// ─── Package row ──────────────────────────────────────────────────────────────

function PackageRow({ pkg, onPatch, busy, index }: { pkg: Package; onPatch: () => void; busy: boolean; index: number }) {
  const [hover, setHover] = useState(false)
  return (
    <tr
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        borderBottom: `1px solid ${colors.border}22`,
        background: hover
          ? `linear-gradient(90deg, ${colors.primary}06 0%, transparent 100%)`
          : 'transparent',
        transition: 'background 0.1s',
        animation: 'pp-fadein 0.25s ease both',
        animationDelay: `${index * 0.03}s`,
      }}
    >
      <td style={{ padding: '10px 16px', color: colors.text, fontFamily: 'monospace', fontSize: '12px' }}>
        {pkg.name}
      </td>
      <td style={{ padding: '10px 16px', color: colors.textMuted, fontFamily: 'monospace', fontSize: '11px' }}>
        {pkg.current_ver ?? '—'}
      </td>
      <td style={{ padding: '10px 16px', fontFamily: 'monospace', fontSize: '11px' }}>
        <span style={{ color: colors.success, textShadow: glow(colors.success, 2) }}>
          {pkg.new_ver ?? '—'}
        </span>
      </td>
      <td style={{ padding: '10px 16px', textAlign: 'right' }}>
        <Button size="sm" onClick={onPatch} disabled={busy}>Update</Button>
      </td>
    </tr>
  )
}

// ─── VmDetail ─────────────────────────────────────────────────────────────────

export function VmDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { role } = useContext(UserContext)
  const canAct = role === 'admin' || role === 'user'
  const isAdmin = role === 'admin'

  const [agent, setAgent] = useState<Agent | null>(null)
  const [packages, setPackages] = useState<Package[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [logJob, setLogJob] = useState<Job | null>(null)
  const [confirm, setConfirm] = useState<{ title: string; message: string; onConfirm: () => void } | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    try {
      const d = await api.agent(id)
      setAgent(d.agent)
      setPackages(d.packages)
      setJobs(d.jobs)
    } catch {
      navigate('/')
    } finally {
      setLoading(false)
    }
  }, [id, navigate])

  useEffect(() => {
    load()
    const t = setInterval(load, 10_000)
    return () => clearInterval(t)
  }, [load])

  const triggerJob = async (type: string, params?: Record<string, unknown>) => {
    if (!id || busy) return
    setBusy(true)
    try {
      await api.createJob(id, type, params)
      setTimeout(load, 1000)
    } catch {
      // error is non-fatal — user can retry
    } finally {
      setBusy(false)
    }
  }

  const acknowledgeConfigReview = async () => {
    if (!id || busy) return
    setBusy(true)
    try {
      await api.acknowledgeConfigReview(id)
      setTimeout(load, 1000)
    } finally {
      setBusy(false)
    }
  }

  const removeAgent = () => {
    if (!id) return
    setConfirm({
      title: 'Remove VM',
      message: `Remove "${agent?.hostname}" from PatchPilot? The agent will need to re-register if reinstalled.`,
      onConfirm: async () => {
        setConfirm(null)
        await api.deleteAgent(id)
        navigate('/')
      },
    })
  }

  const confirmReboot = () => {
    if (!agent) return
    setConfirm({
      title: 'Trigger Reboot',
      message: `Schedule a reboot on "${agent.hostname}"? The system will reboot in 1 minute.`,
      onConfirm: () => {
        setConfirm(null)
        triggerJob('reboot')
      },
    })
  }

  const [renaming, setRenaming] = useState(false)
  const [newId, setNewId] = useState('')
  const [renameError, setRenameError] = useState('')

  const startRename = () => {
    setNewId(id || '')
    setRenameError('')
    setRenaming(true)
  }

  const doRename = async () => {
    if (!id || !newId.trim() || newId === id) { setRenaming(false); return }
    if (!/^[a-zA-Z0-9._-]{1,64}$/.test(newId)) {
      setRenameError('Only a-z A-Z 0-9 . _ - (max 64)')
      return
    }
    try {
      const r = await api.renameAgent(id, newId.trim())
      setRenaming(false)
      navigate(`/vm/${r.new_id}`, { replace: true })
    } catch (e: any) {
      setRenameError(e?.message || 'Rename failed')
    }
  }

  const online = (agent?.seconds_ago ?? 9999) < 120

  if (loading) return <LoadingSkeleton />
  if (!agent) return null

  return (
    <div style={{ padding: 'clamp(16px, 4vw, 32px)', maxWidth: '1400px', animation: 'pp-fadein 0.4s ease both' }}>
      {logJob && <LogModal job={logJob} onClose={() => setLogJob(null)} />}
      {confirm && (
        <ConfirmModal
          title={confirm.title}
          message={confirm.message}
          confirmLabel="Confirm"
          variant="danger"
          onConfirm={confirm.onConfirm}
          onCancel={() => setConfirm(null)}
        />
      )}

      {/* Page header */}
      <PageHeader right={canAct ? (
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          {busy && (
            <span style={{
              width: '10px', height: '10px', borderRadius: '50%',
              border: `1.5px solid ${colors.primary}44`,
              borderTopColor: colors.primary,
              display: 'inline-block',
              animation: 'pp-spin 0.8s linear infinite',
            }} />
          )}
          {agent.reboot_required ? (
            <Button
              variant="danger"
              size="sm"
              loading={busy}
              onClick={confirmReboot}
              disabled={busy}
            >
              ⟳ Reboot
            </Button>
          ) : null}
          {packages.length > 0 && (
            <Button size="sm" onClick={() => triggerJob('patch')} loading={busy} disabled={busy}>
              ↑ Patch All
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setConfirm({
              title: 'Autoremove',
              message: `Run package cleanup on "${agent?.hostname}" to remove unused dependencies?`,
              onConfirm: () => { setConfirm(null); triggerJob('autoremove') },
            })}
            disabled={busy}
            title="Remove unused packages"
          >
            🧹 Clean
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setConfirm({
              title: 'Update Agent',
              message: `Update the PatchPilot agent on "${agent?.hostname}" to the latest version? The agent will restart automatically.`,
              onConfirm: () => { setConfirm(null); triggerJob('update_agent') },
            })}
            disabled={busy}
            title="Update agent binary to latest version"
          >
            ⟳ Agent
          </Button>
        </div>
      ) : undefined}>
        {/* Back arrow */}
        <span
          role="button"
          tabIndex={0}
          aria-label="Back to dashboard"
          onClick={() => navigate('/')}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate('/') } }}
          style={{
            color: colors.textMuted,
            fontWeight: 400,
            marginRight: '10px',
            cursor: 'pointer',
            fontSize: '16px',
            transition: 'color 0.15s',
            fontFamily: 'monospace',
          }}
          onMouseEnter={e => { e.currentTarget.style.color = colors.primary }}
          onMouseLeave={e => { e.currentTarget.style.color = colors.textMuted }}
          title="Back to dashboard"
        >
          ←
        </span>
        {agent.hostname}
      </PageHeader>

      {/* Online status bar + Agent ID */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
        <OnlineDot online={online} />
        <span style={{ color: colors.textMuted, fontSize: '11px', fontFamily: 'monospace' }}>
          {online
            ? `Last seen ${fmtAgo(agent.seconds_ago)}`
            : `Offline since ${fmtAgo(agent.seconds_ago)}`}
        </span>
        <span style={{ color: colors.border }}>│</span>
        {renaming ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '10px', color: colors.textMuted, letterSpacing: '0.1em', textTransform: 'uppercase' }}>ID:</span>
            <input
              value={newId}
              onChange={e => { setNewId(e.target.value.replace(/\s+/g, '-')); setRenameError('') }}
              onKeyDown={e => { if (e.key === 'Enter') doRename(); if (e.key === 'Escape') setRenaming(false) }}
              autoFocus
              maxLength={64}
              style={{
                background: `${colors.bg}cc`, border: `1px solid ${colors.primary}66`,
                color: colors.text, padding: '3px 8px', fontSize: '11px',
                fontFamily: 'monospace', outline: 'none', width: '180px',
              }}
            />
            <Button variant="ghost" size="sm" onClick={doRename}>✓</Button>
            <Button variant="ghost" size="sm" onClick={() => setRenaming(false)}>✕</Button>
            {renameError && <span style={{ fontSize: '10px', color: colors.danger }}>{renameError}</span>}
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '10px', color: colors.textMuted, letterSpacing: '0.1em', textTransform: 'uppercase' }}>ID:</span>
            <code style={{ fontSize: '11px', color: colors.primaryDim, fontFamily: 'monospace' }}>{id}</code>
            {isAdmin && <span
              onClick={startRename}
              title="Rename agent ID"
              style={{
                cursor: 'pointer', fontSize: '11px', color: colors.textMuted,
                transition: 'color 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.color = colors.primary }}
              onMouseLeave={e => { e.currentTarget.style.color = colors.textMuted }}
            >
              ✎
            </span>}
          </div>
        )}
      </div>

      {/* Info cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px', marginBottom: '12px' }}>
        {[
          { label: 'IP Address', value: agent.ip ?? '—', accent: colors.primary },
          { label: 'OS',         value: agent.os_pretty ?? '—', accent: colors.primaryDim },
          { label: 'Package Manager', value: agent.package_manager ?? '—', accent: colors.primaryDim },
          { label: 'Kernel',     value: agent.kernel ?? '—', accent: colors.primaryDim },
          { label: 'Arch',       value: agent.arch ?? '—', accent: colors.primaryDim },
          { label: 'Uptime',     value: fmtUptime(agent.uptime_seconds), accent: colors.primaryDim },
          { label: 'Last Seen',  value: fmtAgo(agent.seconds_ago), accent: colors.primaryDim },
        ].map(({ label, value, accent }, i) => (
          <Card key={label} accent={accent} style={{ padding: '14px 16px', animationDelay: `${i * 0.05}s` }}>
            <div style={{
              fontSize: '10px',
              color: colors.textMuted,
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              marginBottom: '8px',
              fontFamily: "'Orbitron', sans-serif",
            }}>
              {label}
            </div>
            <div style={{
              fontSize: '12px',
              color: colors.text,
              fontFamily: 'monospace',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {value}
            </div>
          </Card>
        ))}
      </div>

      {/* Tags row — only rendered when the agent has at least one tag */}
      {(() => {
        const tagList = (agent.tags ?? '').split(',').map(t => t.trim()).filter(Boolean)
        if (tagList.length === 0) return <div style={{ marginBottom: '12px' }} />
        return (
          <Card accent={colors.primaryDim} style={{ padding: '14px 16px', marginBottom: '12px', animationDelay: '0.2s' }}>
            <div style={{
              fontSize: '10px',
              color: colors.textMuted,
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              marginBottom: '10px',
              fontFamily: "'Orbitron', sans-serif",
            }}>
              Tags
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {tagList.map(tag => (
                <Badge key={tag} color={colors.primaryDim} style={{ fontSize: '10px', padding: '2px 9px' }}>
                  {tag}
                </Badge>
              ))}
            </div>
          </Card>
        )
      })()}

      {/* bottom margin before reboot warning / updates */}
      <div style={{ marginBottom: '12px' }} />

      {/* Reboot warning */}
      {agent.reboot_required && (
        <div style={{
          border: `1px solid ${colors.danger}55`,
          background: `${colors.danger}0a`,
          padding: '14px 18px',
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          fontSize: '12px',
          color: colors.danger,
          textShadow: glow(colors.danger, 3),
          animation: 'pp-fadein 0.3s ease both, pp-warn-pulse 3s ease-in-out infinite',
          fontFamily: "'Electrolize', monospace",
          letterSpacing: '0.06em',
          position: 'relative',
          overflow: 'hidden',
        }}>
          {/* Left accent */}
          <div style={{
            position: 'absolute',
            left: 0, top: 0, bottom: 0,
            width: '3px',
            background: `linear-gradient(180deg, ${colors.danger}, ${colors.danger}44)`,
            boxShadow: `0 0 8px ${colors.danger}`,
          }} />
          <span style={{ fontSize: '16px', marginLeft: '6px' }}>⚠</span>
          <span>This VM requires a reboot to activate installed updates.</span>
        </div>
      )}

      {agent.config_review_required ? (
        <div style={{
          border: `1px solid ${colors.warn}55`,
          background: `${colors.warn}0c`,
          padding: '14px 18px',
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '16px',
          flexWrap: 'wrap',
          fontSize: '12px',
          color: colors.warn,
          textShadow: glow(colors.warn, 3),
          fontFamily: "'Electrolize', monospace",
          letterSpacing: '0.06em',
          position: 'relative',
          overflow: 'hidden',
        }}>
          <div style={{
            position: 'absolute',
            left: 0, top: 0, bottom: 0,
            width: '3px',
            background: `linear-gradient(180deg, ${colors.warn}, ${colors.warn}44)`,
            boxShadow: `0 0 8px ${colors.warn}`,
          }} />
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', flex: '1 1 360px' }}>
            <span style={{ fontSize: '16px', marginLeft: '6px' }}>!</span>
            <div>
              <div style={{ marginBottom: '6px' }}>
                This VM has package config changes that should be reviewed manually.
              </div>
              {agent.config_review_note ? (
                <pre style={{
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  fontSize: '11px',
                  lineHeight: 1.5,
                  color: colors.text,
                  fontFamily: 'monospace',
                }}>
                  {agent.config_review_note}
                </pre>
              ) : null}
            </div>
          </div>
          {canAct ? (
            <Button size="sm" variant="ghost" onClick={acknowledgeConfigReview} disabled={busy}>
              ✓ Reviewed
            </Button>
          ) : null}
        </div>
      ) : null}

      {/* Pending updates */}
      <div style={{ marginBottom: '28px' }}>
        <SectionHeader right={
          packages.length > 0
            ? <Badge color={colors.warn}>{packages.length} Pending</Badge>
            : undefined
        }>
          Pending Updates
        </SectionHeader>

        <div style={{
          border: `1px solid ${colors.border}`,
          background: glassBg(0.65),
          backdropFilter: 'blur(8px)',
          WebkitBackdropFilter: 'blur(8px)',
          overflowX: 'auto',
        }}>
          {packages.length === 0 ? (
            <div style={{
              padding: '44px',
              textAlign: 'center',
              animation: 'pp-fadein 0.4s ease both',
            }}>
              <div style={{ fontSize: '22px', color: colors.success, textShadow: glowStrong(colors.success), marginBottom: '10px' }}>
                ✓
              </div>
              <div style={{ fontSize: '12px', color: colors.success, letterSpacing: '0.18em', fontFamily: "'Orbitron', sans-serif", textShadow: glow(colors.success, 4) }}>
                System Up To Date
              </div>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${colors.border}` }}>
                  {['Package', 'Current Version', 'New Version', ''].map((h, i) => (
                    <th key={i} style={{
                      padding: '10px 16px',
                      textAlign: i === 3 ? 'right' : 'left',
                      fontSize: '10px', letterSpacing: '0.2em', textTransform: 'uppercase',
                      color: colors.textMuted, fontWeight: 500, fontFamily: "'Orbitron', sans-serif",
                    }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {packages.map((pkg, i) => (
                  <PackageRow
                    key={pkg.id}
                    pkg={pkg}
                    index={i}
                    onPatch={() => triggerJob('patch', { packages: [pkg.name] })}
                    busy={busy}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Job history */}
      <div style={{ marginBottom: '32px' }}>
        <SectionHeader right={
          jobs.filter(j => j.status === 'pending').length > 1 && isAdmin ? (
            <Button
              size="sm"
              variant="ghost"
              style={{ color: colors.danger }}
              onClick={() => setConfirm({
                title: 'Cancel All Pending',
                message: `Cancel all ${jobs.filter(j => j.status === 'pending').length} pending jobs for this agent?`,
                onConfirm: async () => {
                  setConfirm(null)
                  try {
                    await api.cancelPendingJobs(id!)
                    load()
                  } catch (e) { console.error(e) }
                },
              })}
            >
              ✕ CANCEL ALL PENDING
            </Button>
          ) : undefined
        }>Job History</SectionHeader>
        <div style={{
          border: `1px solid ${colors.border}`,
          background: glassBg(0.65),
          backdropFilter: 'blur(8px)',
          WebkitBackdropFilter: 'blur(8px)',
          overflowX: 'auto',
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: '50px' }} />
              <col style={{ width: '110px' }} />
              <col style={{ width: '90px' }} />
              <col style={{ width: '150px' }} />
              <col />
              <col style={{ width: '110px' }} />
            </colgroup>
            <thead>
              <tr style={{ borderBottom: `1px solid ${colors.border}` }}>
                {['ID', 'Type', 'Status', 'Finished', 'Output', ''].map((h, i) => (
                  <th key={i} style={{
                    padding: '10px 16px',
                    textAlign: i === 5 ? 'right' : 'left',
                    fontSize: '10px', letterSpacing: '0.2em', textTransform: 'uppercase',
                    color: colors.textMuted, fontWeight: 500, fontFamily: "'Orbitron', sans-serif",
                  }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{
                    padding: '36px',
                    textAlign: 'center',
                    color: colors.textMuted,
                    fontSize: '11px',
                    letterSpacing: '0.14em',
                    fontFamily: "'Orbitron', sans-serif",
                  }}>
                    No jobs yet
                  </td>
                </tr>
              ) : jobs.map((job, idx) => {
                const [statusText, statusColor] = jobStatus(job.status)
                const typeColor = jobTypeColor(job.type)
                const hasLog = !!job.output && ['done', 'failed'].includes(job.status)
                const isRunning = job.status === 'running'
                return (
                  <tr
                    key={job.id}
                    style={{
                      borderBottom: `1px solid ${colors.border}22`,
                      animation: 'pp-fadein 0.25s ease both',
                      animationDelay: `${idx * 0.03}s`,
                    }}
                  >
                    <td style={{ padding: '10px 16px', color: colors.textMuted, fontFamily: 'monospace', fontSize: '11px' }}>
                      #{job.id}
                    </td>
                    <td style={{ padding: '10px 16px' }}>
                      <Badge color={typeColor}>{job.type.toUpperCase()}</Badge>
                    </td>
                    <td style={{ padding: '10px 16px' }}>
                      <span style={{
                        color: statusColor,
                        textShadow: glow(statusColor, 2),
                        fontSize: '11px',
                        letterSpacing: '0.08em',
                        fontFamily: "'Electrolize', monospace",
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '5px',
                      }}>
                        {isRunning && (
                          <span style={{
                            display: 'inline-block',
                            width: '8px', height: '8px',
                            border: `1.5px solid ${statusColor}44`,
                            borderTopColor: statusColor,
                            borderRadius: '50%',
                            animation: 'pp-spin 0.8s linear infinite',
                          }} />
                        )}
                        {statusText}
                      </span>
                    </td>
                    <td style={{ padding: '10px 16px', color: colors.textMuted, fontFamily: 'monospace', fontSize: '11px' }}>
                      {job.finished ?? job.created}
                    </td>
                    <td style={{
                      padding: '10px 16px',
                      color: colors.textDim,
                      fontFamily: 'monospace',
                      fontSize: '11px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {job.output
                        ? job.output.split('\n').find(l => l.trim()) ?? '—'
                        : '—'}
                    </td>
                    <td style={{ padding: '10px 16px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                      {(job.status === 'pending' || job.status === 'running') && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setConfirm({
                            title: 'Cancel Job',
                            message: `Cancel job #${job.id} (${job.type})?`,
                            onConfirm: async () => {
                              setConfirm(null)
                              try {
                                await api.cancelJob(id!, job.id)
                                load()
                              } catch (e) { console.error(e) }
                            },
                          })}
                          style={{ color: colors.danger }}
                        >
                          ✕ Cancel
                        </Button>
                      )}
                      {hasLog && (
                        <Button size="sm" variant="ghost" onClick={() => setLogJob(job)}>
                          ≡ Log
                        </Button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Danger zone — admin only */}
      {isAdmin && <div style={{
        border: `1px solid ${colors.danger}33`,
        background: `${colors.danger}04`,
        animation: 'pp-fadein 0.5s ease both',
      }}>
        <div style={{
          padding: '12px 18px',
          borderBottom: `1px solid ${colors.danger}33`,
          fontSize: '10px',
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
          color: colors.danger,
          fontFamily: "'Orbitron', sans-serif",
          textShadow: glow(colors.danger, 3),
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
        }}>
          <div style={{
            width: '2px', height: '12px',
            background: colors.danger,
            boxShadow: glow(colors.danger, 4),
          }} />
          Danger Zone
        </div>
        <div style={{ padding: '16px 18px' }}>
          <Button variant="danger" onClick={removeAgent}>Remove VM</Button>
        </div>
      </div>}
    </div>
  )
}
