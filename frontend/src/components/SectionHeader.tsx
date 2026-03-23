import React from 'react'
import { colors, glow, glowText, glowStrong } from '../theme'

// ─── Section header (h2 level) ────────────────────────────────────────────────

export function SectionHeader({
  children,
  right,
}: {
  children: React.ReactNode
  right?: React.ReactNode
}) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: '14px',
      gap: '12px',
      flexWrap: 'wrap',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
        {/* Vertical accent bar */}
        <div style={{
          width: '2px',
          height: '14px',
          background: `linear-gradient(180deg, ${colors.primary}, ${colors.primaryDim}44)`,
          boxShadow: glow(colors.primary, 4),
          flexShrink: 0,
        }} />

        <h2 style={{
          margin: 0,
          fontFamily: "'Orbitron', sans-serif",
          fontSize: '11px',
          fontWeight: 600,
          letterSpacing: '0.28em',
          textTransform: 'uppercase',
          color: colors.primary,
          textShadow: glowText(colors.primary, 4),
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>
          {children}
        </h2>
      </div>

      {right && (
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexShrink: 0, flexWrap: 'wrap' }}>
          {right}
        </div>
      )}
    </div>
  )
}

// ─── Page header (h1 level) ───────────────────────────────────────────────────

export function PageHeader({
  children,
  right,
}: {
  children: React.ReactNode
  right?: React.ReactNode
}) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      marginBottom: '28px',
      gap: '16px',
      paddingBottom: '18px',
      borderBottom: `1px solid ${colors.border}`,
      position: 'relative',
      flexWrap: 'wrap',
    }}>
      {/* Animated bottom border glow */}
      <div style={{
        position: 'absolute',
        bottom: -1,
        left: 0,
        width: '120px',
        height: '1px',
        background: `linear-gradient(90deg, ${colors.primary}88, transparent)`,
        boxShadow: `0 0 8px ${colors.primary}44`,
      }} />

      <h1 style={{
        margin: 0,
        fontFamily: "'Orbitron', sans-serif",
        fontSize: 'clamp(14px, 4vw, 20px)',
        fontWeight: 700,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color: colors.text,
        textShadow: glowText(colors.primary, 6),
        lineHeight: 1.2,
      }}>
        {children}
      </h1>

      {right && (
        <div className="pp-page-header-right" style={{
          display: 'flex',
          gap: '8px',
          alignItems: 'center',
          flexShrink: 0,
          paddingTop: '2px',
          flexWrap: 'wrap',
        }}>
          {right}
        </div>
      )}
    </div>
  )
}
