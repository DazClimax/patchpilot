import React, { ReactNode, CSSProperties } from 'react'
import { Animator, FrameCorners } from '@arwes/react'
import { colors, glow, glowStrong, glassBg } from '../theme'

interface CardProps {
  children: ReactNode
  style?: CSSProperties
  accent?: string
  active?: boolean
  /** Add a subtle glow border animation */
  animated?: boolean
}

export function Card({
  children,
  style,
  accent = colors.primary,
  active = true,
  animated = false,
}: CardProps) {
  return (
    <Animator active={active}>
      <div style={{
        position: 'relative',
        background: glassBg(0.6),
        backdropFilter: 'blur(10px)',
        WebkitBackdropFilter: 'blur(10px)',
        padding: '20px',
        color: accent,
        animation: 'pp-fadein 0.35s ease both',
        ...(animated ? { animation: 'pp-fadein 0.35s ease both, pp-glow-border 4s ease-in-out infinite' } : {}),
        ...style,
      }}>
        {/* FrameCorners SVG — corner brackets only, no fill */}
        <FrameCorners
          strokeWidth={1.5}
          cornerLength={16}
          styled={false}
          positioned
          style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
        />

        {/* Top-left micro corner accent */}
        <div style={{
          position: 'absolute',
          top: 0, left: 0,
          width: '8px', height: '8px',
          borderTop: `1px solid ${accent}88`,
          borderLeft: `1px solid ${accent}88`,
          pointerEvents: 'none',
        }} />
        <div style={{
          position: 'absolute',
          bottom: 0, right: 0,
          width: '8px', height: '8px',
          borderBottom: `1px solid ${accent}44`,
          borderRight: `1px solid ${accent}44`,
          pointerEvents: 'none',
        }} />

        {/* Content — reset to text color */}
        <div style={{ position: 'relative', color: colors.text }}>
          {children}
        </div>
      </div>
    </Animator>
  )
}

// ─── Skeleton loader ───────────────────────────────────────────────────────────

export function SkeletonCard({ height = 80 }: { height?: number }) {
  return (
    <div style={{
      position: 'relative',
      height,
      background: glassBg(0.4),
      backdropFilter: 'blur(6px)',
      overflow: 'hidden',
    }}>
      {/* Shimmer sweep */}
      <div style={{
        position: 'absolute',
        inset: 0,
        background: `linear-gradient(
          90deg,
          transparent 0%,
          ${colors.primary}0a 40%,
          ${colors.primary}18 50%,
          ${colors.primary}0a 60%,
          transparent 100%
        )`,
        backgroundSize: '400px 100%',
        animation: 'pp-shimmer 1.8s linear infinite',
      }} />
      {/* Corner brackets */}
      <div style={{
        position: 'absolute', top: 0, left: 0,
        width: '14px', height: '14px',
        borderTop: `1px solid ${colors.border}`,
        borderLeft: `1px solid ${colors.border}`,
      }} />
      <div style={{
        position: 'absolute', bottom: 0, right: 0,
        width: '14px', height: '14px',
        borderBottom: `1px solid ${colors.border}`,
        borderRight: `1px solid ${colors.border}`,
      }} />
    </div>
  )
}

// ─── Stat card ────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string
  value: string | number
  accent?: string
  sub?: string
  loading?: boolean
}

export function StatCard({
  label,
  value,
  accent = colors.primary,
  sub,
  loading = false,
}: StatCardProps) {
  if (loading) return <SkeletonCard height={90} />

  return (
    <Card accent={accent} animated>
      {/* Label */}
      <div style={{
        fontSize: '10px',
        color: colors.textMuted,
        letterSpacing: '0.22em',
        textTransform: 'uppercase',
        marginBottom: '10px',
        fontFamily: "'Orbitron', sans-serif",
      }}>
        {label}
      </div>

      {/* Value */}
      <div style={{
        fontFamily: "'Orbitron', sans-serif",
        fontSize: 'clamp(24px, 6vw, 34px)',
        fontWeight: 800,
        color: accent,
        textShadow: glowStrong(accent),
        lineHeight: 1,
        letterSpacing: '-0.01em',
      }}>
        {value}
        {sub && (
          <span style={{
            fontSize: '15px',
            color: colors.textDim,
            fontWeight: 400,
            marginLeft: '6px',
            letterSpacing: '0.02em',
          }}>
            {sub}
          </span>
        )}
      </div>

      {/* Bottom accent bar */}
      <div style={{
        position: 'absolute',
        bottom: 0,
        left: '20px',
        right: '20px',
        height: '1px',
        background: `linear-gradient(90deg, transparent, ${accent}55, transparent)`,
      }} />
    </Card>
  )
}
