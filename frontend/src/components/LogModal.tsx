import React, { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Animator, FrameCorners } from '@arwes/react'
import { colors, glow, glowText, glassBg } from '../theme'
import { Job } from '../api/client'

interface LogModalProps {
  job: Job
  onClose: () => void
}

const statusColor = (s: string) => ({
  done:    colors.success,
  failed:  colors.danger,
  running: colors.warn,
}[s] ?? colors.textDim)

const statusIcon = (s: string) => ({
  done:    '✓',
  failed:  '✗',
  running: '⟳',
}[s] ?? '·')

export function LogModal({ job, onClose }: LogModalProps) {
  const logRef = useRef<HTMLDivElement>(null)
  const modalRef = useRef<HTMLDivElement>(null)
  const [copied, setCopied] = useState(false)

  // Close on Escape + focus trap
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key === 'Tab' && modalRef.current) {
        const focusable = modalRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        )
        if (focusable.length === 0) return
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault(); last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault(); first.focus()
        }
      }
    }
    window.addEventListener('keydown', handler)
    // Focus the modal on mount
    modalRef.current?.focus()
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // Scroll to bottom on mount
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [])

  const sc = statusColor(job.status)
  const si = statusIcon(job.status)
  const lines = (job.output ?? '(no output)').split('\n')

  const copyLog = async () => {
    const text = (job.output ?? '(no output)').replace(/\r\n/g, '\n')
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        const textarea = document.createElement('textarea')
        textarea.value = text
        textarea.setAttribute('readonly', '')
        textarea.style.position = 'absolute'
        textarea.style.left = '-9999px'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        document.body.removeChild(textarea)
      }
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1400)
    } catch {
      // non-fatal
    }
  }

  return createPortal(
    <>
      {/* Backdrop — centers modal via flex */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 200,
          background: 'rgba(2,12,14,0.88)',
          backdropFilter: 'blur(6px)',
          WebkitBackdropFilter: 'blur(6px)',
          animation: 'pp-fadein 0.2s ease both',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
          boxSizing: 'border-box',
          overflowY: 'auto',
        }}
      >

      {/* Modal */}
      <Animator active>
        <div
          ref={modalRef}
          role="dialog"
          aria-modal="true"
          aria-label="Job log"
          tabIndex={-1}
          onClick={e => e.stopPropagation()}
          style={{
            position: 'relative',
            width: 'min(900px, 94vw)',
            maxHeight: 'calc(100dvh - 48px)',
            display: 'flex',
            flexDirection: 'column',
            background: glassBg(0.97),
            backdropFilter: 'blur(16px)',
            WebkitBackdropFilter: 'blur(16px)',
            boxShadow: `0 0 60px ${colors.primary}14, 0 0 100px rgba(0,0,0,0.9), inset 0 0 40px ${colors.primary}04`,
            animation: 'pp-fadein 0.25s ease both',
          }}>

          {/* Arwes corner brackets on the modal */}
          <FrameCorners
            strokeWidth={1.5}
            cornerLength={20}
            styled={false}
            positioned
            style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 1, color: colors.primary }}
          />

          {/* Top glow line */}
          <div style={{
            position: 'absolute',
            top: 0, left: 0, right: 0,
            height: '1px',
            background: `linear-gradient(90deg, transparent, ${colors.primary}88, transparent)`,
            zIndex: 2,
          }} />

          {/* Header */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 22px',
            borderBottom: `1px solid ${colors.border}`,
            flexShrink: 0,
            zIndex: 2,
            position: 'relative',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
              {/* Job label */}
              <span style={{
                fontFamily: "'Orbitron', sans-serif",
                fontSize: '12px',
                letterSpacing: '0.22em',
                color: colors.primary,
                textShadow: glowText(colors.primary, 4),
              }}>
                JOB #{job.id}
              </span>

              {/* Divider */}
              <span style={{ color: colors.textMuted, fontSize: '10px' }}>|</span>

              {/* Type + status badge */}
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                fontSize: '10px',
                letterSpacing: '0.12em',
                fontFamily: "'Electrolize', monospace",
                color: sc,
                textShadow: glowText(sc, 3),
                border: `1px solid ${sc}44`,
                padding: '2px 10px',
                background: `${sc}0e`,
                clipPath: 'polygon(4px 0%, 100% 0%, calc(100% - 4px) 100%, 0% 100%)',
              }}>
                <span style={{
                  animation: job.status === 'running' ? 'pp-spin 1s linear infinite' : 'none',
                  display: 'inline-block',
                }}>
                  {si}
                </span>
                {job.type.toUpperCase()} — {job.status.toUpperCase()}
              </span>

              {/* Timestamp */}
              {job.finished && (
                <span style={{
                  fontSize: '10px',
                  color: colors.textMuted,
                  fontFamily: 'monospace',
                  letterSpacing: '0.05em',
                }}>
                  {job.finished}
                </span>
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                onClick={copyLog}
                style={{
                  background: copied ? `${colors.primary}12` : 'none',
                  border: `1px solid ${copied ? colors.primary : colors.border}`,
                  color: copied ? colors.primary : colors.textDim,
                  cursor: 'pointer',
                  padding: '4px 12px',
                  fontSize: '11px',
                  fontFamily: "'Orbitron', sans-serif",
                  lineHeight: 1,
                  letterSpacing: '0.14em',
                  textTransform: 'uppercase',
                  transition: 'all 0.15s',
                  clipPath: 'polygon(4px 0%, 100% 0%, calc(100% - 4px) 100%, 0% 100%)',
                  boxShadow: copied ? `0 0 10px ${colors.primary}33` : 'none',
                }}
                onMouseEnter={e => {
                  if (copied) return
                  e.currentTarget.style.borderColor = colors.primary
                  e.currentTarget.style.color = colors.primary
                  e.currentTarget.style.background = `${colors.primary}10`
                  e.currentTarget.style.boxShadow = `0 0 8px ${colors.primary}33`
                }}
                onMouseLeave={e => {
                  if (copied) return
                  e.currentTarget.style.borderColor = colors.border
                  e.currentTarget.style.color = colors.textDim
                  e.currentTarget.style.background = 'none'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                {copied ? 'Copied' : 'Copy Log'}
              </button>
              <button
                onClick={onClose}
                style={{
                  background: 'none',
                  border: `1px solid ${colors.border}`,
                  color: colors.textDim,
                  cursor: 'pointer',
                  padding: '4px 12px',
                  fontSize: '13px',
                  fontFamily: 'monospace',
                  lineHeight: 1,
                  transition: 'all 0.15s',
                  clipPath: 'polygon(4px 0%, 100% 0%, calc(100% - 4px) 100%, 0% 100%)',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.borderColor = colors.danger
                  e.currentTarget.style.color = colors.danger
                  e.currentTarget.style.background = `${colors.danger}10`
                  e.currentTarget.style.boxShadow = `0 0 8px ${colors.danger}44`
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.borderColor = colors.border
                  e.currentTarget.style.color = colors.textDim
                  e.currentTarget.style.background = 'none'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                ✕
              </button>
            </div>
          </div>

          {/* Log output */}
          <div
            ref={logRef}
            style={{
              flex: 1,
              overflow: 'auto',
              padding: '14px 20px',
              fontFamily: "'Courier New', Courier, monospace",
              fontSize: '12px',
              lineHeight: '1.75',
              background: glassBg(0.95),
              position: 'relative',
              zIndex: 2,
              // Custom scrollbar handled globally via scrollbarCSS in Layout
            }}
          >
            {/* Scanline overlay on log area */}
            <div style={{
              position: 'absolute',
              inset: 0,
              pointerEvents: 'none',
              background: `repeating-linear-gradient(
                0deg,
                transparent,
                transparent 2px,
                rgba(0,0,0,0.04) 2px,
                rgba(0,0,0,0.04) 4px
              )`,
              zIndex: 1,
            }} />

            <div style={{ position: 'relative', zIndex: 2 }}>
              {lines.map((line, i) => {
                const isError = /error|fail|E:/i.test(line)
                const isWarn  = /warn|W:/i.test(line)
                const isOk    = /^Setting up|^Unpacking|installed|done/i.test(line)
                const color   = isError ? colors.danger
                              : isWarn  ? colors.warn
                              : isOk    ? colors.success
                              : colors.textDim

                return (
                  <div key={i} style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '0',
                    color,
                    minHeight: '1.4em',
                    textShadow: (isError || isOk) ? glow(color, 2) : 'none',
                    animation: `pp-fadein 0.15s ease both`,
                    animationDelay: `${Math.min(i * 0.008, 0.4)}s`,
                  }}>
                    {/* Line number */}
                    <span style={{
                      color: colors.textMuted,
                      userSelect: 'none',
                      marginRight: '14px',
                      fontSize: '10px',
                      lineHeight: '1.75',
                      minWidth: '28px',
                      textAlign: 'right',
                      flexShrink: 0,
                      opacity: 0.6,
                    }}>
                      {String(i + 1).padStart(3, ' ')}
                    </span>
                    {/* Line content */}
                    <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                      {line || '\u00A0'}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Footer */}
          <div style={{
            padding: '10px 22px',
            borderTop: `1px solid ${colors.border}`,
            flexShrink: 0,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontSize: '10px',
            color: colors.textMuted,
            fontFamily: "'Electrolize', monospace",
            letterSpacing: '0.08em',
            zIndex: 2,
            position: 'relative',
          }}>
            <span>{lines.length} lines</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <kbd style={{
                padding: '1px 6px',
                border: `1px solid ${colors.border}`,
                fontSize: '9px',
                letterSpacing: '0.06em',
                background: `${colors.bgCard}`,
                color: colors.textDim,
              }}>
                ESC
              </kbd>
              to close
            </span>
          </div>
        </div>
      </Animator>
      </div>
    </>,
    document.body,
  )
}
