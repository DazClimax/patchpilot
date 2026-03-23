import React, { createContext, useContext, useState, useCallback, useRef } from 'react'
import { colors, glow } from '../theme'

interface ToastItem {
  id: number
  message: string
  type: 'error' | 'success' | 'info'
}

interface ToastContextValue {
  showToast: (message: string, type?: 'error' | 'success' | 'info') => void
}

const ToastContext = createContext<ToastContextValue>({ showToast: () => {} })

export function useToast() {
  return useContext(ToastContext)
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const counterRef = useRef(0)

  const showToast = useCallback((message: string, type: 'error' | 'success' | 'info' = 'info') => {
    const id = ++counterRef.current
    setToasts(prev => [...prev, { id, message, type }])
    const duration = type === 'error' ? 8000 : 4000
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), duration)
  }, [])

  const typeColors = {
    error: colors.danger,
    success: colors.success,
    info: colors.primary,
  }

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div role="status" aria-live="polite" style={{
        position: 'fixed',
        bottom: '80px',
        right: '16px',
        left: '16px',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-end',
        gap: '8px',
        pointerEvents: 'none',
      }}>
        {toasts.map(t => {
          const c = typeColors[t.type]
          return (
            <div key={t.id} style={{
              padding: '10px 16px',
              background: `rgba(2,12,14,0.96)`,
              border: `1px solid ${c}66`,
              color: c,
              fontFamily: "'Electrolize', monospace",
              fontSize: '12px',
              letterSpacing: '0.06em',
              boxShadow: `0 0 20px ${c}22, 0 4px 24px rgba(0,0,0,0.8)`,
              animation: 'pp-fadein 0.25s ease both',
              maxWidth: '340px',
              lineHeight: 1.5,
            }}>
              {t.message}
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}
