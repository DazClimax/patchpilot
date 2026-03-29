import React, { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Animator, FrameCorners } from '@arwes/react'
import { colors, glow, glowText, glassBg } from '../theme'
import { Button } from './Button'

interface ConfirmModalProps {
  title: string
  message: string
  confirmLabel?: string
  variant?: 'danger' | 'primary'
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmModal({
  title,
  message,
  confirmLabel = 'OK',
  variant = 'danger',
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  const accentColor = variant === 'danger' ? colors.danger : colors.primary
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
      // Focus trap
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
  }, [onCancel])

  const modal = (
    <>
      {/* Backdrop */}
      <div
        onClick={onCancel}
        style={{
          position: 'fixed', inset: 0, zIndex: 200,
          background: `${colors.bg}d9`,
          backdropFilter: 'blur(6px)',
          WebkitBackdropFilter: 'blur(6px)',
          animation: 'pp-fadein 0.2s ease both',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {/* Modal panel — stopPropagation so clicks inside don't close */}
        <Animator active>
          <div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="pp-confirm-title"
            onClick={e => e.stopPropagation()}
            style={{
              position: 'relative',
              width: 'min(420px, 92vw)',
              background: glassBg(0.97),
              backdropFilter: 'blur(16px)',
              WebkitBackdropFilter: 'blur(16px)',
              boxShadow: `0 0 60px ${accentColor}18, 0 0 120px ${colors.bg}f2, inset 0 0 40px ${accentColor}05`,
              animation: 'pp-fadein 0.22s ease both',
            }}
          >
            {/* Arwes corner brackets */}
            <FrameCorners
              strokeWidth={1.5}
              cornerLength={16}
              styled={false}
              positioned
              style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 1, color: accentColor }}
            />

            {/* Top glow line */}
            <div style={{
              position: 'absolute',
              top: 0, left: 0, right: 0,
              height: '1px',
              background: `linear-gradient(90deg, transparent, ${accentColor}99, transparent)`,
              zIndex: 2,
            }} />

            {/* Header */}
            <div style={{
              padding: '16px 22px',
              borderBottom: `1px solid ${colors.border}`,
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              position: 'relative',
              zIndex: 2,
            }}>
              {/* Accent bar */}
              <div style={{
                width: '2px', height: '14px', flexShrink: 0,
                background: accentColor,
                boxShadow: `0 0 8px ${accentColor}`,
              }} />
              <span id="pp-confirm-title" style={{
                fontFamily: "'Orbitron', sans-serif",
                fontSize: '11px',
                letterSpacing: '0.22em',
                color: accentColor,
                textShadow: glowText(accentColor, 4),
                textTransform: 'uppercase',
              }}>
                {title}
              </span>
            </div>

            {/* Body */}
            <div style={{
              padding: '22px 22px 18px',
              fontSize: '13px',
              color: colors.text,
              fontFamily: "'Electrolize', monospace",
              lineHeight: 1.6,
              letterSpacing: '0.04em',
              position: 'relative',
              zIndex: 2,
            }}>
              {message}
            </div>

            {/* Footer buttons */}
            <div style={{
              padding: '14px 22px 18px',
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '10px',
              position: 'relative',
              zIndex: 2,
            }}>
              <Button
                autoFocus
                size="sm"
                variant="ghost"
                onClick={onCancel}
              >
                Cancel
              </Button>

              <Button
                size="sm"
                variant={variant}
                onClick={onConfirm}
              >
                {confirmLabel}
              </Button>
            </div>
          </div>
        </Animator>
      </div>
    </>
  )

  if (typeof document === 'undefined') return modal
  return createPortal(modal, document.body)
}
