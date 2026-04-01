import React, { ReactNode, useState, useEffect, useRef, useContext } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  Animator,
  AnimatorGeneralProvider,
  Dots,
  MovingLines,
  useBleeps,
} from '@arwes/react'
import { colors, glow, glowText, glowStrong, globalKeyframes, scrollbarCSS } from '../theme'
import { auth, Role } from '../api/client'
import { UserContext } from '../App'

type NavItem = { to: string; label: string; icon: string; minRole?: Role }

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: '⬡' },
  { to: '/schedule', label: 'Schedules', icon: '◷', minRole: 'user' },
  { to: '/deploy', label: 'Deploy', icon: '⊕', minRole: 'admin' },
  { to: '/settings', label: 'Settings', icon: '⚙', minRole: 'admin' },
  { to: '/users', label: 'Users', icon: '👤', minRole: 'admin' },
  { to: '/about', label: 'About', icon: 'ⓘ' },
]

const ROLE_LEVELS: Record<Role, number> = { readonly: 0, user: 1, admin: 2 }

function NavItem({ to, label, icon }: { to: string; label: string; icon: string }) {
  const loc = useLocation()
  const bleeps = useBleeps()
  const active = loc.pathname === to || (to !== '/' && loc.pathname.startsWith(to))
  const [hover, setHover] = useState(false)
  const lit = active || hover

  return (
    <Link
      to={to}
      onClick={() => bleeps.click?.play()}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '10px 16px',
        textDecoration: 'none',
        fontSize: '12px',
        fontFamily: "'Electrolize', monospace",
        letterSpacing: '0.12em',
        color: lit ? colors.primary : colors.textDim,
        background: active
          ? `linear-gradient(90deg, ${colors.primary}12 0%, transparent 100%)`
          : hover
          ? `${colors.primary}07`
          : 'transparent',
        borderLeft: `2px solid ${active ? colors.primary : hover ? colors.primaryDim : 'transparent'}`,
        transition: 'all 0.18s ease',
        textShadow: lit ? glowText(colors.primary, 5) : 'none',
        animation: 'pp-fadein 0.3s ease both',
        position: 'relative',
      }}
    >
      <span style={{
        fontSize: '15px',
        opacity: lit ? 1 : 0.45,
        textShadow: lit ? glow(colors.primary, 6) : 'none',
        transition: 'all 0.18s ease',
      }}>
        {icon}
      </span>
      <span className="pp-nav-label" style={{ textTransform: 'uppercase' }}>{label}</span>
      {active && (
        <span className="pp-active-dot" style={{
          position: 'absolute',
          right: '12px',
          width: '4px',
          height: '4px',
          borderRadius: '50%',
          background: colors.primary,
          boxShadow: glowStrong(colors.primary),
        }} />
      )}
    </Link>
  )
}

function useServerOnline() {
  const [online, setOnline] = useState<boolean | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const check = async () => {
    try {
      const res = await fetch('/api/ping', { method: 'GET' })
      setOnline(res.ok)
    } catch {
      setOnline(false)
    }
  }

  useEffect(() => {
    check()
    timerRef.current = setInterval(check, 15_000)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [])

  return online
}

export function Layout({ children }: { children: ReactNode }) {
  const serverOnline = useServerOnline()
  const { role, username } = useContext(UserContext)
  const filteredNav = NAV.filter(n => !n.minRole || ROLE_LEVELS[role] >= ROLE_LEVELS[n.minRole])

  return (
    <AnimatorGeneralProvider duration={{ enter: 0.45, exit: 0.3 }}>
      <Animator active>
        <style>{globalKeyframes}{scrollbarCSS}{`
          * { box-sizing: border-box; }
          body { margin: 0; background: ${colors.bg}; }
          ::selection { background: ${colors.primary}33; color: ${colors.primary}; }
          input::placeholder { color: ${colors.textMuted}; }
          input:focus, select:focus, textarea:focus {
            border-color: ${colors.primary}88 !important;
            box-shadow: 0 0 6px ${colors.primary}33;
          }
          select option { background: ${colors.bgCard}; color: ${colors.text}; }
          @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after {
              animation-duration: 0.01ms !important;
              animation-iteration-count: 1 !important;
              transition-duration: 0.01ms !important;
            }
          }
          @media (max-width: 640px) {
            .pp-layout-root { flex-direction: column !important; }
            .pp-page-header-right {
              flex-basis: 100% !important;
              flex-shrink: 1 !important;
            }
            .pp-hide-mobile {
              display: none !important;
            }
            .pp-sidebar {
              width: 100% !important;
              height: auto !important;
              flex-direction: row !important;
              order: 2 !important;
              position: fixed !important;
              bottom: 0 !important;
              left: 0 !important;
              right: 0 !important;
              z-index: 100 !important;
              border-right: none !important;
              border-top: 1px solid ${colors.border} !important;
            }
            .pp-sidebar .pp-logo-area,
            .pp-sidebar .pp-nav-section-label,
            .pp-sidebar .pp-sidebar-art,
            .pp-sidebar .pp-system-status,
            .pp-sidebar .pp-signout,
            .pp-sidebar .pp-footer,
            .pp-sidebar .pp-edge-glow-top,
            .pp-sidebar .pp-edge-glow-bottom,
            .pp-sidebar .pp-corner-accent { display: none !important; }
            .pp-sidebar .pp-mobile-signout {
              display: flex !important;
            }
            .pp-sidebar nav {
              flex-direction: row !important;
              justify-content: space-around !important;
              padding: 0 !important;
              gap: 0 !important;
              width: 100% !important;
              flex: unset !important;
            }
            .pp-sidebar nav a {
              flex-direction: column !important;
              padding: 10px 8px !important;
              gap: 4px !important;
              border-left: none !important;
              font-size: 9px !important;
              flex: 1 !important;
              text-align: center !important;
              justify-content: center !important;
              align-items: center !important;
              min-height: 56px !important;
            }
            .pp-sidebar .pp-mobile-signout {
              flex-direction: column !important;
              padding: 10px 8px !important;
              gap: 4px !important;
              font-size: 9px !important;
              flex: 1 !important;
              text-align: center !important;
              justify-content: center !important;
              align-items: center !important;
              min-height: 56px !important;
              border: none !important;
              border-left: none !important;
              margin: 0 !important;
              width: auto !important;
              background: transparent !important;
            }
            .pp-sidebar nav a .pp-active-dot { display: none !important; }
            .pp-main-content {
              padding-bottom: 124px !important;
            }
            .pp-content-footer {
              display: none !important;
            }
            input, select, textarea {
              font-size: 16px !important;
            }
          }
          @media (min-width: 641px) {
            .pp-mobile-signout {
              display: none !important;
            }
          }
        `}</style>

        <div className="pp-layout-root" style={{ display: 'flex', minHeight: '100vh', height: '100dvh', overflow: 'hidden', position: 'relative' }}>

          {/* Ambient dot grid */}
          <div style={{ position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none', opacity: 0.12 }}>
            <Dots color={colors.primary} size={1} distance={30} />
          </div>

          {/* Ambient moving lines */}
          <div style={{ position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none', opacity: 0.05 }}>
            <MovingLines lineColor={colors.primary} lineWidth={1} sets={4} />
          </div>

          {/* Scan-line sweep — very subtle */}
          <div style={{
            position: 'fixed',
            inset: 0,
            zIndex: 1,
            pointerEvents: 'none',
            background: `repeating-linear-gradient(
              0deg,
              transparent,
              transparent 2px,
              ${colors.bg}08 2px,
              ${colors.bg}08 4px
            )`,
          }} />

          {/* Sidebar */}
          <aside className="pp-sidebar" style={{
            width: '220px',
            flexShrink: 0,
            background: `linear-gradient(180deg, ${colors.bgCard}f2 0%, ${colors.bg}fa 100%)`,
            borderRight: `1px solid ${colors.border}`,
            display: 'flex',
            flexDirection: 'column',
            zIndex: 10,
            backdropFilter: 'blur(12px)',
            WebkitBackdropFilter: 'blur(12px)',
            position: 'relative',
            animation: 'pp-slideright 0.4s ease both',
          }}>

            {/* Top edge glow line */}
            <div className="pp-edge-glow-top" style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: '1px',
              background: `linear-gradient(90deg, transparent 0%, ${colors.primary}66 50%, transparent 100%)`,
            }} />

            {/* Logo */}
            <div className="pp-logo-area" style={{
              padding: '22px 20px 18px',
              borderBottom: `1px solid ${colors.border}`,
              position: 'relative',
            }}>
              {/* Corner accent */}
              <div className="pp-corner-accent" style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '20px',
                height: '20px',
                borderTop: `2px solid ${colors.primary}`,
                borderLeft: `2px solid ${colors.primary}`,
                opacity: 0.8,
              }} />

              <div className="pp-logo-text" style={{
                fontFamily: "'Orbitron', sans-serif",
                fontSize: '17px',
                fontWeight: 800,
                letterSpacing: '0.12em',
                color: colors.primary,
                textShadow: glowStrong(colors.primary),
                lineHeight: 1.2,
              }}>
                PATCH<span style={{ color: colors.text, textShadow: 'none' }}>PILOT</span>
              </div>
              <div style={{
                fontSize: '9px',
                color: colors.textMuted,
                letterSpacing: '0.25em',
                textTransform: 'uppercase',
                marginTop: '5px',
                fontFamily: "'Electrolize', monospace",
              }}>
                Linux Patch Management
              </div>

              {/* Blinking cursor + logged-in user */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '12px' }}>
                <span style={{
                  display: 'inline-block',
                  width: '6px',
                  height: '11px',
                  background: colors.primary,
                  animation: 'pp-blink 1.2s step-end infinite',
                  boxShadow: glow(colors.primary, 4),
                  flexShrink: 0,
                }} />
                {username && <span style={{
                  fontSize: '10px',
                  color: colors.primary,
                  fontFamily: "'Electrolize', monospace",
                  letterSpacing: '0.08em',
                }}>{username}</span>}
              </div>
            </div>

            {/* Nav section label */}
            <div className="pp-nav-section-label" style={{
              padding: '14px 20px 6px',
              fontSize: '9px',
              letterSpacing: '0.3em',
              textTransform: 'uppercase',
              color: colors.textMuted,
              fontFamily: "'Orbitron', sans-serif",
            }}>
              Navigation
            </div>

            {/* Nav */}
            <nav style={{
              flex: 1,
              padding: '4px 8px',
              display: 'flex',
              flexDirection: 'column',
              gap: '2px',
            }}>
              {filteredNav.map(n => <NavItem key={n.to} {...n} />)}
              <button
                className="pp-mobile-signout"
                onClick={() => { auth.clear(); window.location.href = '/login' }}
                aria-label="Sign out"
                style={{
                  display: 'none',
                  color: colors.danger,
                  cursor: 'pointer',
                  fontFamily: "'Electrolize', monospace",
                  letterSpacing: '0.12em',
                  textTransform: 'uppercase',
                  position: 'relative',
                }}
              >
                <span style={{
                  fontSize: '15px',
                  opacity: 0.9,
                  textShadow: glow(colors.danger, 6),
                  transition: 'all 0.18s ease',
                }}>
                  ↩
                </span>
                <span className="pp-nav-label">Logout</span>
              </button>
            </nav>

            <div className="pp-sidebar-art" style={{
              margin: '0 12px 12px',
              border: `1px solid ${colors.border}`,
              background: `${colors.bgCard}88`,
              overflow: 'hidden',
              boxShadow: `0 0 18px ${colors.primary}18`,
            }}>
              <img
                src="/about-hero.png"
                alt="PatchPilot artwork"
                style={{
                  display: 'block',
                  width: '100%',
                  height: 'auto',
                }}
              />
            </div>

            {/* System status indicator */}
            <div className="pp-system-status" style={{
              margin: '0 12px 12px',
              padding: '10px 12px',
              border: `1px solid ${serverOnline === false ? colors.danger + '55' : colors.border}`,
              background: serverOnline === false ? `${colors.danger}0d` : `${colors.bgCard}88`,
              fontSize: '10px',
              fontFamily: "'Electrolize', monospace",
              transition: 'border-color 0.4s, background 0.4s',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                <span style={{
                  width: '5px', height: '5px', borderRadius: '50%',
                  background: serverOnline === false ? colors.danger : colors.success,
                  boxShadow: glow(serverOnline === false ? colors.danger : colors.success, 4),
                  animation: serverOnline === false
                    ? 'pp-pulse 1.2s ease-in-out infinite'
                    : serverOnline === true
                    ? 'none'
                    : 'pp-pulse 2.5s ease-in-out infinite',
                }} />
                <span style={{
                  color: serverOnline === false ? colors.danger : colors.textDim,
                  letterSpacing: '0.1em',
                  transition: 'color 0.3s',
                }}>
                  {serverOnline === false ? 'SERVER OFFLINE' : 'SYSTEM ONLINE'}
                </span>
              </div>
              <div style={{ color: colors.textMuted, letterSpacing: '0.06em' }}>
                {serverOnline === false ? 'Connection lost' : 'Auto-refresh active'}
              </div>
            </div>

            {/* Sign Out */}
            <button
              className="pp-signout"
              onClick={() => { auth.clear(); window.location.href = '/login' }}
              aria-label="Sign out"
              style={{
                margin: '0 12px 8px',
                padding: '8px 12px',
                background: 'transparent',
                border: `1px solid ${colors.border}`,
                color: colors.textMuted,
                cursor: 'pointer',
                fontSize: '10px',
                fontFamily: "'Electrolize', monospace",
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                width: 'calc(100% - 24px)',
                textAlign: 'left',
                transition: 'all 0.15s',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = colors.danger
                e.currentTarget.style.color = colors.danger
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = colors.border
                e.currentTarget.style.color = colors.textMuted
              }}
            >
              ↩ Sign Out
            </button>

            {/* Footer */}
            <div className="pp-footer" style={{
              padding: '10px 20px',
              borderTop: `1px solid ${colors.border}`,
              fontSize: '10px',
              color: colors.textMuted,
              letterSpacing: '0.1em',
              fontFamily: "'Electrolize', monospace",
            }}>
              v1.6.5
            </div>

            {/* Bottom edge glow line */}
            <div className="pp-edge-glow-bottom" style={{
              position: 'absolute',
              bottom: 0,
              left: 0,
              right: 0,
              height: '1px',
              background: `linear-gradient(90deg, transparent 0%, ${colors.border} 50%, transparent 100%)`,
            }} />
          </aside>

          {/* Main content */}
          <main className="pp-main-content" style={{
            flex: 1,
            overflow: 'hidden',
            zIndex: 5,
            position: 'relative',
            animation: 'pp-fadein 0.5s ease both',
            display: 'flex',
            flexDirection: 'column',
          }}>
            <div style={{ flex: 1, overflow: 'auto' }}>
              {children}
            </div>

            {/* Content footer — fixed at bottom, same height as sidebar version */}
            <footer className="pp-content-footer" style={{
              padding: '10px 20px',
              borderTop: `1px solid ${colors.border}`,
              fontSize: '10px',
              color: colors.textMuted,
              fontFamily: "'Electrolize', monospace",
              letterSpacing: '0.08em',
              display: 'flex',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '8px',
              flexShrink: 0,
            }}>
              <span>PatchPilot {new Date().getFullYear()}</span>
              <span>
                find me on{' '}
                <a
                  href="https://github.com/DazClimax/patchpilot"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: colors.primary, textDecoration: 'none' }}
                >
                  GitHub
                </a>
              </span>
            </footer>
          </main>

        </div>
      </Animator>
    </AnimatorGeneralProvider>
  )
}
