import React, { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { colors, glow, glowText, glassBg, controlStyles } from '../theme'

export interface DropdownOption {
  value: string
  label: string
}

interface DropdownProps {
  value: string
  onChange: (v: string) => void
  options: DropdownOption[]
  placeholder?: string
  disabled?: boolean
}

export function Dropdown({ value, onChange, options, placeholder, disabled = false }: DropdownProps) {
  const [open, setOpen] = useState(false)
  const [focused, setFocused] = useState(false)
  const [menuStyle, setMenuStyle] = useState<React.CSSProperties | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  const selected = options.find(o => o.value === value)

  useEffect(() => {
    if (!open || !ref.current) return

    const updatePosition = () => {
      if (!ref.current) return
      const rect = ref.current.getBoundingClientRect()
      setMenuStyle({
        position: 'fixed',
        top: rect.bottom + 2,
        left: rect.left,
        width: rect.width,
        zIndex: 1000,
      })
    }

    updatePosition()
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition, true)
    }
  }, [open])

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      const insideTrigger = !!ref.current?.contains(target)
      const insideMenu = !!menuRef.current?.contains(target)
      if (!insideTrigger && !insideMenu) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open])

  const borderColor = open || focused ? colors.primary : colors.border
  const boxShadow   = open || focused
    ? `0 0 0 1px ${colors.primary}44, inset 0 0 12px ${colors.primary}08`
    : 'none'

  return (
    <div ref={ref} style={{ position: 'relative', width: '100%' }}>
      {/* Trigger */}
      <button
        type="button"
        disabled={disabled}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onClick={() => {
          if (disabled) return
          setOpen(o => !o)
        }}
        style={{
          width: '100%',
          minHeight: controlStyles.minHeight,
          padding: `${controlStyles.paddingY} 34px ${controlStyles.paddingY} ${controlStyles.paddingX}`,
          boxSizing: 'border-box',
          background: colors.bg,
          border: `1px solid ${borderColor}`,
          color: disabled ? colors.textMuted : (selected ? colors.text : colors.textMuted),
          fontFamily: "'Electrolize', monospace",
          fontSize: controlStyles.fontSize,
          lineHeight: controlStyles.lineHeight,
          letterSpacing: '0.05em',
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.65 : 1,
          textAlign: 'left',
          outline: 'none',
          transition: 'border-color 0.15s, box-shadow 0.15s',
          boxShadow,
          position: 'relative',
        }}
      >
        {selected?.label ?? placeholder ?? '—'}

        {/* Chevron */}
        <span style={{
          position: 'absolute',
          right: '10px',
          top: '50%',
          transform: `translateY(-50%) rotate(${open ? '180deg' : '0deg'})`,
          transition: 'transform 0.18s',
          color: disabled ? colors.textDim : (open ? colors.primary : colors.textMuted),
          fontSize: '10px',
          lineHeight: 1,
          textShadow: disabled ? 'none' : (open ? glow(colors.primary, 4) : 'none'),
        }}>
          ▾
        </span>
      </button>

      {/* Dropdown list */}
      {open && menuStyle && typeof document !== 'undefined' && createPortal((
        <div
          ref={menuRef}
          style={{
            ...menuStyle,
            background: glassBg(0.98),
            backdropFilter: 'blur(16px)',
            WebkitBackdropFilter: 'blur(16px)',
            border: `1px solid ${colors.primary}55`,
            boxShadow: `0 8px 32px rgba(0,0,0,0.8), 0 0 20px ${colors.primary}10`,
            animation: 'pp-fadein 0.12s ease both',
            overflow: 'hidden',
          }}
        >
          {/* Top glow line */}
          <div style={{
            position: 'absolute', top: 0, left: 0, right: 0,
            height: '1px',
            background: `linear-gradient(90deg, transparent, ${colors.primary}88, transparent)`,
          }} />

          {options.map((opt, i) => {
            const isSelected = opt.value === value
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => { onChange(opt.value); setOpen(false) }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  width: '100%',
                  padding: '10px 14px',
                  background: isSelected ? `${colors.primary}14` : 'transparent',
                  border: 'none',
                  borderBottom: i < options.length - 1 ? `1px solid ${colors.border}44` : 'none',
                  color: isSelected ? colors.primary : colors.text,
                  fontFamily: "'Electrolize', monospace",
                  fontSize: '13px',
                  letterSpacing: '0.05em',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'background 0.1s, color 0.1s',
                  textShadow: isSelected ? glowText(colors.primary, 3) : 'none',
                }}
                onMouseEnter={e => {
                  if (!isSelected) {
                    e.currentTarget.style.background = `${colors.primary}0a`
                    e.currentTarget.style.color = colors.text
                  }
                }}
                onMouseLeave={e => {
                  if (!isSelected) {
                    e.currentTarget.style.background = 'transparent'
                  }
                }}
              >
                {/* Selected indicator */}
                <span style={{
                  width: '4px', height: '4px',
                  borderRadius: '50%',
                  background: isSelected ? colors.primary : 'transparent',
                  boxShadow: isSelected ? glow(colors.primary, 4) : 'none',
                  flexShrink: 0,
                  transition: 'all 0.15s',
                }} />
                {opt.label}
              </button>
            )
          })}
        </div>
      ), document.body)}
    </div>
  )
}
