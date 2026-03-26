import React, { useState, useEffect, createContext } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { VmDetail } from './pages/VmDetail'
import { SchedulePage } from './pages/Schedule'
import { SettingsPage } from './pages/Settings'
import { DeployPage } from './pages/Deploy'
import { AboutPage } from './pages/About'
import { UsersPage } from './pages/Users'
import { LoginPage } from './pages/Login'
import { auth, Role } from './api/client'
import { ToastProvider } from './components/Toast'
import { ErrorBoundary } from './components/ErrorBoundary'
import { UiEffectsProvider } from './effects'

export const UserContext = createContext<{ role: Role; username: string }>({
  role: 'readonly',
  username: '',
})

export default function App() {
  const [authed, setAuthed] = useState(() => {
    const match = window.location.hash.match(/[#&]pp-key=([^&]*)/)
    if (match) {
      auth.setKey(decodeURIComponent(match[1]))
      history.replaceState(null, '', window.location.pathname + window.location.search)
    }
    return auth.isSet()
  })

  const [role, setRole] = useState<Role>(auth.getRole())
  const [username, setUsername] = useState(auth.getUsername())

  useEffect(() => {
    const onStorage = () => setAuthed(auth.isSet())
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const handleLogin = () => {
    setAuthed(true)
    setRole(auth.getRole())
    setUsername(auth.getUsername())
  }

  return (
    <ErrorBoundary>
    <UiEffectsProvider>
    <ToastProvider>
    <BrowserRouter>
      <UserContext.Provider value={{ role, username }}>
      <Routes>
        <Route path="/login" element={
          authed
            ? <Navigate to="/" replace />
            : <LoginPage onLogin={handleLogin} />
        } />
        <Route path="/*" element={
          authed
            ? <Layout>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/vm/:id" element={<VmDetail />} />
                  <Route path="/schedule" element={role !== 'readonly' ? <SchedulePage /> : <Navigate to="/" replace />} />
                  <Route path="/settings" element={role === 'admin' ? <SettingsPage /> : <Navigate to="/" replace />} />
                  <Route path="/deploy" element={role === 'admin' ? <DeployPage /> : <Navigate to="/" replace />} />
                  <Route path="/users" element={role === 'admin' ? <UsersPage /> : <Navigate to="/" replace />} />
                  <Route path="/about" element={<AboutPage />} />
                </Routes>
              </Layout>
            : <Navigate to="/login" replace />
        } />
      </Routes>
      </UserContext.Provider>
    </BrowserRouter>
    </ToastProvider>
    </UiEffectsProvider>
    </ErrorBoundary>
  )
}
