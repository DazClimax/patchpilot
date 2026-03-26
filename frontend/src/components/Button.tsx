import React, { ButtonHTMLAttributes, CSSProperties } from 'react'
import { colors, glow, glowStrong } from '../theme'
import { useBleeps } from '@arwes/react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'danger' | 'ghost'
  size?: 'sm' | 'md'
  /** Show a spinning loader inside the button */
  loading?: boolean
}

const variants = {
  primary: {
    color:  colors.primary,
    bg:     `${colors.primary}12`,
    border: `${colors.primary}55`,
    hoverBg:`${colors.primary}22`,
  },
  danger: {
    color:  colors.danger,
    bg:     `${colors.danger}12`,
    border: `${colors.danger}55`,
    hoverBg:`${colors.danger}22`,
  },
  ghost: {
    color:  colors.textDim,
    bg:     'transparent',
    border: colors.border,
    hoverBg:`${colors.primary}0a`,
  },
}

export function Button({
  variant = 'primary',
  size = 'md',
  style,
  children,
  loading = false,
  disabled,
  onClick,
  ...rest
}: ButtonProps) {
  const bleeps = useBleeps()
  const v = variants[variant]
  const padding  = size === 'sm' ? '6px 10px'  : '10px 18px'
  const fontSize = size === 'sm' ? '10px'       : '12px'
  const isDisabled = disabled || loading

  const baseStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    padding,
    fontSize,
    fontFamily: "'Electrolize', monospace",
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    color: v.color,
    background: v.bg,
    border: `1px solid ${v.border}`,
    cursor: isDisabled ? 'not-allowed' : 'pointer',
    textShadow: glow(v.color, 3),
    boxShadow: `inset 0 0 8px ${v.color}0a`,
    transition: 'all 0.15s ease',
    outline: 'none',
    opacity: isDisabled ? 0.45 : 1,
    position: 'relative',
    overflow: 'hidden',
    // Chamfered corners via clip-path
    clipPath: 'polygon(6px 0%, 100% 0%, calc(100% - 6px) 100%, 0% 100%)',
    ...style,
  }

  return (
    <button
      style={baseStyle}
      disabled={isDisabled}
      onClick={e => {
        if (!isDisabled) bleeps.click?.play()
        onClick?.(e)
      }}
      onMouseEnter={e => {
        if (isDisabled) return
        const el = e.currentTarget
        el.style.background = v.hoverBg
        el.style.borderColor = v.color
        el.style.boxShadow = `${glow(v.color, 8)}, inset 0 0 14px ${v.color}12`
        el.style.textShadow = glowStrong(v.color)
      }}
      onMouseLeave={e => {
        if (isDisabled) return
        const el = e.currentTarget
        el.style.background = v.bg
        el.style.borderColor = v.border
        el.style.boxShadow = `inset 0 0 8px ${v.color}0a`
        el.style.textShadow = glow(v.color, 3)
      }}
      onMouseDown={e => {
        if (isDisabled) return
        e.currentTarget.style.transform = 'scale(0.97)'
      }}
      onMouseUp={e => {
        e.currentTarget.style.transform = 'scale(1)'
      }}
      onFocus={e => {
        if (isDisabled) return
        const el = e.currentTarget
        el.style.background = v.hoverBg
        el.style.borderColor = v.color
        el.style.boxShadow = `${glow(v.color, 8)}, inset 0 0 14px ${v.color}12`
        el.style.textShadow = glowStrong(v.color)
        el.style.outline = `2px solid ${v.color}66`
        el.style.outlineOffset = '2px'
      }}
      onBlur={e => {
        const el = e.currentTarget
        el.style.background = v.bg
        el.style.borderColor = v.border
        el.style.boxShadow = `inset 0 0 8px ${v.color}0a`
        el.style.textShadow = glow(v.color, 3)
        el.style.outline = 'none'
      }}
      {...rest}
    >
      {loading && (
        <span style={{
          display: 'inline-block',
          width: size === 'sm' ? '9px' : '11px',
          height: size === 'sm' ? '9px' : '11px',
          border: `1.5px solid ${v.color}44`,
          borderTopColor: v.color,
          borderRadius: '50%',
          animation: 'pp-spin 0.7s linear infinite',
          flexShrink: 0,
        }} />
      )}
      {children}
    </button>
  )
}
