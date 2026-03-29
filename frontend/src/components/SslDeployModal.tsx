import React, { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Animator, FrameCorners } from '@arwes/react'
import { colors, glow, glowText, glassBg } from '../theme'
import { Button } from './Button'

export interface DeployStatus {
  agents: Array<{
    agent_id: string
    hostname: string
    job_type?: string
    status: string
    phase: string
    output: string
    finished: string | null
    online: boolean
  }>
  total: number
  total_online: number
  completed: number
}

export function SslDeployModal({
  deployStatus,
  sslEnabled,
  sslAvailable,
  busy,
  hideOfflinePending = false,
  title = 'SSL Certificate Deployment',
  inProgressText = 'Updating agents and deploying certificate...',
  doneLabel = 'CERT INSTALLED',
  activePhaseLabel = 'INSTALLING CERT...',
  waitingLabel = 'AGENT UPDATED',
  summaryVerb = 'installed',
  onClose,
  onRetry,
  onEnableHttps,
}: {
  deployStatus: DeployStatus | null
  sslEnabled?: boolean
  sslAvailable?: boolean
  busy: boolean
  hideOfflinePending?: boolean
  title?: string
  inProgressText?: string
  doneLabel?: string
  activePhaseLabel?: string
  waitingLabel?: string
  summaryVerb?: string
  onClose: () => void
  onRetry: () => void
  onEnableHttps?: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const onlineTotal = deployStatus ? (deployStatus.total_online ?? deployStatus.total) : 0
  const allOnlineDone = deployStatus != null && onlineTotal > 0 && deployStatus.completed >= onlineTotal
  const isDone = allOnlineDone || (deployStatus != null && !busy)
  const visibleAgents = deployStatus
    ? deployStatus.agents.filter(a => !(hideOfflinePending && !a.online && a.status !== 'failed'))
    : []

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
            boxShadow: `0 0 60px ${colors.primary}18, 0 0 120px ${colors.bg}f2, inset 0 0 40px ${colors.primary}05`,
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
              {title}
            </span>
          </div>

          <div style={{ padding: '22px 22px 18px', position: 'relative', zIndex: 2 }}>
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
                  {inProgressText}
                </div>
              ) : visibleAgents.map(a => {
                const phase = a.phase || a.status
                const isHaAutoUpdate = a.job_type === 'ha_trigger_agent_update'
                const isOffline = !a.online
                const isPending = a.status === 'pending' || phase === 'pending'
                const label = a.status === 'done' ? (isHaAutoUpdate ? 'HA UPDATE COMPLETED' : doneLabel)
                  : a.status === 'failed' ? 'FAILED'
                  : phase === 'triggering' ? 'TRIGGERING HA UPDATE...'
                  : isHaAutoUpdate && phase === 'waiting' ? 'WAITING FOR HA RESTART...'
                  : phase === 'updating' ? 'UPDATING AGENT...'
                  : phase === 'waiting' ? waitingLabel
                  : phase === 'deploying' ? activePhaseLabel
                  : isOffline && isPending ? 'OFFLINE — WAITING'
                  : 'PENDING'
                const dotColor = a.status === 'done' ? colors.success
                  : a.status === 'failed' ? colors.danger
                  : (phase === 'triggering' || phase === 'waiting' || phase === 'updating' || phase === 'deploying') ? colors.warn
                  : isOffline ? colors.textMuted
                  : colors.textMuted
                const isActive = phase === 'triggering' || phase === 'waiting' || phase === 'updating' || phase === 'deploying'
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
                        <span style={{ fontSize: 'clamp(9px, 0.85vw, 10px)', marginLeft: '6px', color: colors.textMuted }}>●  OFFLINE</span>
                      )}
                    </span>
                    <span style={{ fontSize: 'clamp(9px, 0.85vw, 10px)', letterSpacing: '0.1em', color: dotColor }}>
                      {label}
                    </span>
                  </div>
                )
              })}
            </div>

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

          <div style={{
            padding: '14px 22px 18px',
            display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
            gap: '10px', flexWrap: 'wrap',
            position: 'relative', zIndex: 2,
            borderTop: `1px solid ${colors.border}`,
          }}>
            {isDone ? (
              <>
                {deployStatus && (
                  <span style={{
                    fontSize: '10px', fontFamily: "'Electrolize', monospace",
                    color: hasFailed ? colors.warn : colors.success,
                    letterSpacing: '0.06em', marginRight: 'auto',
                  }}>
                    {deployStatus.agents.filter(a => a.status === 'done').length} {summaryVerb}
                    {hasFailed ? ` · ${deployStatus.agents.filter(a => a.status === 'failed').length} failed` : ''}
                    {hideOfflinePending && deployStatus.total > onlineTotal ? ` · ${deployStatus.total - onlineTotal} offline hidden` : ''}
                  </span>
                )}
                {hasFailed && (
                  <Button variant="ghost" onClick={onRetry}>Retry Failed</Button>
                )}
                {!sslEnabled && sslAvailable && onEnableHttps && (
                  <Button disabled={busy} onClick={onEnableHttps}>Enable HTTPS</Button>
                )}
                <Button variant="primary" onClick={onClose}>Close</Button>
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
