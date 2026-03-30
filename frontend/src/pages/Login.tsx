import React, { useState } from 'react'
import { Animator, AnimatorGeneralProvider, Dots, MovingLines, useBleeps } from '@arwes/react'
import { auth, api } from '../api/client'
import { colors, glow, glowText, glassBg, globalKeyframes, controlStyles } from '../theme'
import { useUiEffects } from '../effects'

interface LoginPageProps {
  onLogin: () => void
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const bleeps = useBleeps()
  const { loginAnimationEnabled, loginBackgroundAnimationEnabled, loginBackgroundOpacity } = useUiEffects()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [loginFxActive, setLoginFxActive] = useState(false)
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
      if (loginAnimationEnabled) {
        setLoginFxActive(true)
        window.setTimeout(() => onLogin(), 3200)
      } else {
        onLogin()
      }
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
    minHeight: controlStyles.minHeight,
    padding: `${controlStyles.paddingY} 14px`,
    background: `${colors.bg}cc`,
    border: `1px solid ${error ? colors.danger : colors.border}`,
    color: colors.text,
    fontFamily: "'Electrolize', monospace",
    fontSize: controlStyles.fontSize,
    lineHeight: controlStyles.lineHeight,
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
      <style>{globalKeyframes}{`
        @keyframes pp-login-window {
          0% {
            opacity: 0;
            transform: translate(-50%, -50%) scale(0.2);
            clip-path: inset(49% 49% 49% 49%);
          }
          20% {
            opacity: 1;
            transform: translate(-50%, -50%) scale(0.45);
            clip-path: inset(34% 38% 34% 38%);
          }
          42% {
            opacity: 1;
            transform: translate(-50%, -50%) scale(0.78);
            clip-path: inset(14% 18% 14% 18%);
          }
          62% {
            opacity: 1;
            transform: translate(-50%, -50%) scale(1);
            clip-path: inset(0% 0% 0% 0%);
          }
          100% {
            opacity: 1;
            transform: translate(-50%, -50%) scale(1);
            clip-path: inset(0% 0% 0% 0%);
          }
        }
        @keyframes pp-login-corner {
          0% { opacity: 0; transform: scale(0.2); }
          28% { opacity: 1; transform: scale(1.1); }
          100% { opacity: 1; transform: scale(1); }
        }
        @keyframes pp-login-frame-glow {
          0% { opacity: 0; box-shadow: 0 0 0 ${colors.primary}00; }
          30% { opacity: 1; box-shadow: 0 0 28px ${colors.primary}22, inset 0 0 28px ${colors.primary}12; }
          100% { opacity: 1; box-shadow: 0 0 36px ${colors.primary}18, inset 0 0 36px ${colors.primary}10; }
        }
        @keyframes pp-login-title {
          0% { opacity: 0; transform: translateY(10px) scale(0.96); }
          18% { opacity: 0; transform: translateY(10px) scale(0.96); }
          24% { opacity: 1; transform: translateY(0) scale(1); }
          30% { opacity: 0.25; transform: translateY(0) scale(1); }
          36% { opacity: 1; transform: translateY(0) scale(1); }
          42% { opacity: 0.25; transform: translateY(0) scale(1); }
          48% { opacity: 1; transform: translateY(0) scale(1); }
          72% { opacity: 1; transform: translateY(0) scale(1); }
          100% { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
      <AnimatorGeneralProvider duration={{ enter: 0.4, exit: 0.3 }}>
        <Animator active>
          <div style={{
            minHeight: '100vh',
            height: '100dvh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: colors.bg,
            position: 'relative',
            overflow: 'hidden',
          }}>
            {loginFxActive && (
              <div style={{
                position: 'fixed',
                inset: 0,
                zIndex: 30,
                pointerEvents: 'none',
                overflow: 'hidden',
                background: `radial-gradient(circle at center, ${colors.primary}0d 0%, ${colors.bg}cc 55%, ${colors.bg} 100%)`,
                animation: 'pp-fadein 0.1s ease both',
              }}>
                <div style={{
                  position: 'absolute',
                  left: '50%',
                  top: '50%',
                  width: '100vw',
                  height: '100dvh',
                  transform: 'translate(-50%, -50%)',
                  border: `1px solid ${colors.primary}28`,
                  background: `linear-gradient(180deg, ${colors.bg}f0 0%, ${colors.bg}dc 100%)`,
                  animation: 'pp-login-window 1.05s cubic-bezier(0.22, 1, 0.36, 1) forwards, pp-login-frame-glow 1.05s ease-out forwards',
                }}>
                  <div style={{
                    position: 'absolute',
                    top: 18,
                    left: 18,
                    width: '34px',
                    height: '34px',
                    borderTop: `2px solid ${colors.primary}`,
                    borderLeft: `2px solid ${colors.primary}`,
                    opacity: 0.9,
                    boxShadow: `0 0 12px ${colors.primary}44`,
                    animation: 'pp-login-corner 1.05s ease-out forwards',
                  }} />
                  <div style={{
                    position: 'absolute',
                    top: 18,
                    right: 18,
                    width: '34px',
                    height: '34px',
                    borderTop: `2px solid ${colors.primary}`,
                    borderRight: `2px solid ${colors.primary}`,
                    opacity: 0.9,
                    boxShadow: `0 0 12px ${colors.primary}44`,
                    animation: 'pp-login-corner 1.05s ease-out forwards',
                  }} />
                  <div style={{
                    position: 'absolute',
                    bottom: 18,
                    left: 18,
                    width: '34px',
                    height: '34px',
                    borderBottom: `2px solid ${colors.primary}`,
                    borderLeft: `2px solid ${colors.primary}`,
                    opacity: 0.75,
                    boxShadow: `0 0 12px ${colors.primary}30`,
                    animation: 'pp-login-corner 1.05s ease-out forwards',
                  }} />
                  <div style={{
                    position: 'absolute',
                    bottom: 18,
                    right: 18,
                    width: '34px',
                    height: '34px',
                    borderBottom: `2px solid ${colors.primary}`,
                    borderRight: `2px solid ${colors.primary}`,
                    opacity: 0.75,
                    boxShadow: `0 0 12px ${colors.primary}30`,
                    animation: 'pp-login-corner 1.05s ease-out forwards',
                  }} />
                  <div style={{
                    position: 'absolute',
                    top: 18,
                    left: 56,
                    right: 56,
                    height: '1px',
                    background: `linear-gradient(90deg, transparent 0%, ${colors.primary}88 50%, transparent 100%)`,
                    boxShadow: `0 0 10px ${colors.primary}44`,
                    opacity: 0.9,
                  }} />
                  <div style={{
                    position: 'absolute',
                    inset: 0,
                    background: `radial-gradient(circle at top left, ${colors.primary}12, transparent 34%)`,
                    opacity: 0.8,
                  }} />
                </div>
                <div style={{
                  position: 'absolute',
                  inset: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  <div style={{
                    padding: '12px 22px',
                    background: `${colors.bg}bb`,
                    color: colors.primary,
                    fontFamily: "'Orbitron', sans-serif",
                    fontSize: '11px',
                    letterSpacing: '0.28em',
                    textTransform: 'uppercase',
                    textShadow: glowText(colors.primary, 6),
                    animation: 'pp-login-title 3.9s ease-out forwards',
                  }}>
                    System Access Granted
                  </div>
                </div>
              </div>
            )}
            {/* Ambient background */}
            <div style={{ position: 'absolute', inset: 0, opacity: loginBackgroundAnimationEnabled ? 0.08 : 0.12, pointerEvents: 'none' }}>
              <Dots color={colors.primary} size={1} distance={30} />
            </div>
            {loginBackgroundAnimationEnabled && (
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  opacity: loginBackgroundOpacity / 100,
                  pointerEvents: 'none',
                  background: `radial-gradient(circle at top, ${colors.primary}10 0%, transparent 58%, ${colors.bg} 100%)`,
                }}
              >
                <MovingLines lineColor={colors.primary} lineWidth={1} sets={4} />
              </div>
            )}

            {/* Login card */}
            {!loginFxActive && <div style={{
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
                  onClick={() => { if (canSubmit && !loading) bleeps.click?.play() }}
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
            </div>}
          </div>
        </Animator>
      </AnimatorGeneralProvider>
    </>
  )
}
