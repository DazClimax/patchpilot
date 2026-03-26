import React, { CSSProperties } from 'react'
import { colors, glow, glowText } from '../theme'

interface BadgeProps {
  children: React.ReactNode
  color?: string
  style?: CSSProperties
  className?: string
}

export function Badge({ children, color = colors.primary, style, className }: BadgeProps) {
  return (
    <span className={className} style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '4px',
      padding: '2px 9px',
      fontSize: '10px',
      fontFamily: "'Electrolize', monospace",
      letterSpacing: '0.12em',
      textTransform: 'uppercase',
      color,
      border: `1px solid ${color}55`,
      background: `${color}10`,
      textShadow: glowText(color, 3),
      boxShadow: `inset 0 0 8px ${color}0d, 0 0 6px ${color}18`,
      // Clip-path gives a subtle skewed tech look (tiny chamfered corners)
      clipPath: 'polygon(4px 0%, 100% 0%, calc(100% - 4px) 100%, 0% 100%)',
      ...style,
    }}>
      {children}
    </span>
  )
}

// ─── Status dot with animated pulse ──────────────────────────────────────────

export function OnlineDot({ online }: { online: boolean }) {
  const color = online ? colors.success : colors.danger

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '7px',
      fontSize: '11px',
      fontFamily: "'Electrolize', monospace",
      letterSpacing: '0.1em',
      color,
      textShadow: online ? glowText(color, 3) : 'none',
    }}>
      {/* Outer ring + inner dot */}
      <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{
          position: 'absolute',
          width: '12px',
          height: '12px',
          borderRadius: '50%',
          border: `1px solid ${color}`,
          boxShadow: glow(color, 4),
          animation: 'pp-pulse 2.2s ease-in-out infinite',
          opacity: 0.5,
        }} />
        <span style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: color,
          boxShadow: `0 0 6px ${color}, 0 0 12px ${color}66`,
        }} />
      </span>
      <span className="pp-hide-mobile" style={{ textTransform: 'uppercase' }}>
        {online ? 'Online' : 'Offline'}
      </span>
    </span>
  )
}
