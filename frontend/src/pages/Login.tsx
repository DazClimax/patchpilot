import React, { useState } from 'react'
import { Animator, Dots, MovingLines } from '@arwes/react'
import { AnimatorGeneralProvider } from '@arwes/react'
import { auth, api } from '../api/client'
import { colors, glow, glowText, glassBg, globalKeyframes } from '../theme'

interface LoginPageProps {
  onLogin: () => void
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [mode, setMode] = useState<'login' | 'key'>('login')

  // Legacy admin key login
  const [key, setKey] = useState('')

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      if (mode === 'key') {
        if (!key.trim()) return
        auth.setKey(key.trim())
        await api.dashboard()
        auth.setSession('', 'admin', 'admin')
      } else {
        if (!username.trim() || !password) return
        const res = await api.login(username.trim(), password)
        auth.setSession(res.token, res.role, res.username)
      }
      onLogin()
    } catch (err) {
      auth.clear()
      const msg = err instanceof Error ? err.message : 'Login failed'
      setError(mode === 'key' ? 'Invalid admin key' : msg)
    } finally {
      setLoading(false)
    }
  }

  const canSubmit = mode === 'key' ? !!key.trim() : !!(username.trim() && password)

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '10px 14px',
    background: `${colors.bg}cc`,
    border: `1px solid ${error ? colors.danger : colors.border}`,
    color: colors.text,
    fontFamily: "'Electrolize', monospace",
    fontSize: '13px',
    letterSpacing: '0.06em',
    outline: 'none',
    marginBottom: '8px',
    boxSizing: 'border-box',
    transition: 'border-color 0.15s',
  }

  const labelStyle: React.CSSProperties = {
    fontSize: '9px',
    color: colors.textMuted,
    letterSpacing: '0.25em',
    textTransform: 'uppercase',
    fontFamily: "'Orbitron', sans-serif",
    marginBottom: '8px',
  }

  return (
    <>
      <style>{globalKeyframes}</style>
      <AnimatorGeneralProvider duration={{ enter: 0.4, exit: 0.3 }}>
        <Animator active>
          <div style={{
            height: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: colors.bg,
            position: 'relative',
            overflow: 'hidden',
          }}>
            {/* Ambient background */}
            <div style={{ position: 'absolute', inset: 0, opacity: 0.12, pointerEvents: 'none' }}>
              <Dots color={colors.primary} size={1} distance={30} />
            </div>
            <div style={{ position: 'absolute', inset: 0, opacity: 0.05, pointerEvents: 'none' }}>
              <MovingLines lineColor={colors.primary} lineWidth={1} sets={2} />
            </div>

            {/* Login card */}
            <div style={{
              position: 'relative',
              zIndex: 10,
              width: 'min(420px, 92vw)',
              background: glassBg(0.95),
              backdropFilter: 'blur(16px)',
              border: `1px solid ${colors.border}`,
              boxShadow: `0 0 60px ${colors.primary}14, 0 0 120px rgba(0,0,0,0.8)`,
              animation: 'pp-fadein 0.5s ease both',
            }}>
              {/* Top glow line */}
              <div style={{
                height: '1px',
                background: `linear-gradient(90deg, transparent, ${colors.primary}88, transparent)`,
                boxShadow: `0 0 8px ${colors.primary}44`,
              }} />

              {/* Header */}
              <div style={{ padding: '36px 36px 28px', textAlign: 'center', borderBottom: `1px solid ${colors.border}` }}>
                <div style={{
                  fontFamily: "'Orbitron', sans-serif",
                  fontSize: '24px',
                  fontWeight: 700,
                  letterSpacing: '0.12em',
                  color: colors.primary,
                  textShadow: glowText(colors.primary, 8),
                  marginBottom: '6px',
                }}>
                  PATCH<span style={{ color: colors.text }}>PILOT</span>
                </div>
                <div style={{
                  fontSize: '10px',
                  color: colors.textMuted,
                  letterSpacing: '0.3em',
                  textTransform: 'uppercase',
                  fontFamily: "'Orbitron', sans-serif",
                }}>
                  Patch Management
                </div>
              </div>

              {/* Form */}
              <form onSubmit={handleLogin} style={{ padding: '28px 36px 32px' }}>
                {mode === 'login' ? (
                  <>
                    <div style={labelStyle}>Username</div>
                    <input
                      type="text"
                      value={username}
                      onChange={e => setUsername(e.target.value)}
                      placeholder="Enter username..."
                      autoFocus
                      autoComplete="username"
                      style={inputStyle}
                    />
                    <div style={{ ...labelStyle, marginTop: '12px' }}>Password</div>
                    <input
                      type="password"
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      placeholder="Enter password..."
                      autoComplete="current-password"
                      style={inputStyle}
                    />
                  </>
                ) : (
                  <>
                    <div style={labelStyle}>Admin Key</div>
                    <input
                      type="password"
                      value={key}
                      onChange={e => setKey(e.target.value)}
                      placeholder="Enter admin key..."
                      autoFocus
                      style={inputStyle}
                    />
                  </>
                )}

                {error && (
                  <div style={{
                    fontSize: '11px',
                    color: colors.danger,
                    textShadow: glow(colors.danger, 3),
                    marginBottom: '14px',
                    letterSpacing: '0.06em',
                    animation: 'pp-fadein 0.2s ease both',
                  }}>
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={loading || !canSubmit}
                  style={{
                    width: '100%',
                    marginTop: error ? 0 : '14px',
                    padding: '11px',
                    background: loading ? `${colors.primary}15` : `${colors.primary}18`,
                    border: `1px solid ${colors.primary}88`,
                    color: colors.primary,
                    fontFamily: "'Orbitron', sans-serif",
                    fontSize: '11px',
                    letterSpacing: '0.22em',
                    textTransform: 'uppercase',
                    cursor: loading ? 'not-allowed' : 'pointer',
                    textShadow: glowText(colors.primary, 4),
                    boxShadow: `0 0 12px ${colors.primary}18`,
                    transition: 'all 0.15s',
                    opacity: !canSubmit ? 0.5 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                  }}
                >
                  {loading && (
                    <span style={{
                      width: '10px', height: '10px',
                      border: `1.5px solid ${colors.primary}44`,
                      borderTopColor: colors.primary,
                      borderRadius: '50%',
                      display: 'inline-block',
                      animation: 'pp-spin 0.8s linear infinite',
                    }} />
                  )}
                  {loading ? 'Authenticating...' : 'Sign In'}
                </button>

                <div style={{
                  marginTop: '20px',
                  fontSize: '10px',
                  color: colors.textMuted,
                  textAlign: 'center',
                  letterSpacing: '0.05em',
                }}>
                  <span
                    onClick={() => { setMode(m => m === 'login' ? 'key' : 'login'); setError('') }}
                    style={{ cursor: 'pointer', color: colors.primary, textDecoration: 'none' }}
                  >
                    {mode === 'login' ? 'Use admin key instead' : 'Use username + password'}
                  </span>
                </div>
              </form>
            </div>
          </div>
        </Animator>
      </AnimatorGeneralProvider>
    </>
  )
}
