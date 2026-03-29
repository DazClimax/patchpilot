import React from 'react'
import { colors, glassBg } from '../theme'
import { Button } from './Button'

interface State { hasError: boolean; error: Error | null }

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  State
> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '60vh',
        padding: '32px',
      }}>
        <div style={{
          background: glassBg(0.95),
          border: `1px solid ${colors.danger}44`,
          padding: '32px 40px',
          maxWidth: '520px',
          textAlign: 'center',
          fontFamily: "'Electrolize', monospace",
        }}>
          <div style={{
            fontSize: '14px',
            color: colors.danger,
            fontFamily: "'Orbitron', sans-serif",
            letterSpacing: '0.15em',
            marginBottom: '16px',
          }}>
            SYSTEM ERROR
          </div>
          <div style={{ fontSize: '12px', color: colors.textDim, marginBottom: '20px', lineHeight: 1.6 }}>
            {this.state.error?.message || 'An unexpected error occurred.'}
          </div>
          <Button variant="danger" onClick={() => window.location.reload()}>
            RELOAD
          </Button>
        </div>
      </div>
    )
  }
}
