import React, { useEffect, useState, useCallback } from 'react'
import { api, User } from '../api/client'
import { colors, glassBg, controlStyles } from '../theme'
import { Card } from '../components/Card'
import { Button } from '../components/Button'
import { Dropdown } from '../components/Dropdown'
import { PageHeader, SectionHeader } from '../components/SectionHeader'
import { ConfirmModal } from '../components/ConfirmModal'
import { useToast } from '../components/Toast'

const inputStyle: React.CSSProperties = {
  width: '100%',
  minHeight: controlStyles.minHeight,
  padding: controlStyles.padding,
  boxSizing: 'border-box',
  background: colors.bg,
  border: `1px solid ${colors.border}`,
  color: colors.text,
  fontFamily: "'Electrolize', monospace",
  fontSize: controlStyles.fontSize,
  lineHeight: controlStyles.lineHeight,
  outline: 'none',
  letterSpacing: '0.04em',
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 'clamp(9px, 0.95vw, 10px)',
  letterSpacing: '0.2em',
  textTransform: 'uppercase',
  fontFamily: "'Orbitron', sans-serif",
  color: colors.textMuted,
  marginBottom: '6px',
}

export function UsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [newUser, setNewUser] = useState({ username: '', password: '', role: 'user' })
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string>('')
  const [resetId, setResetId] = useState<number | null>(null)
  const [resetPw, setResetPw] = useState('')
  const [deleteUser, setDeleteUser] = useState<User | null>(null)
  const { showToast } = useToast()

  const load = useCallback(async () => {
    setLoadError('')
    try {
      const res = await api.users()
      setUsers(Array.isArray(res.users) ? res.users : [])
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load users'
      setUsers([])
      setLoadError(message)
      showToast(message, 'error')
    }
    finally { setLoading(false) }
  }, [showToast])

  useEffect(() => { load() }, [load])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newUser.username.trim() || !newUser.password) return
    try {
      await api.createUser(newUser)
      setNewUser({ username: '', password: '', role: 'user' })
      showToast('User created', 'success')
      load()
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to create user', 'error')
    }
  }

  const handleDelete = async (user: User) => {
    try {
      await api.deleteUser(user.id)
      showToast('User deleted', 'success')
      load()
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to delete user', 'error')
    }
  }

  const handleRoleChange = async (user: User, newRole: string) => {
    try {
      await api.updateUser(user.id, { role: newRole })
      showToast(`${user.username} → ${newRole}`, 'success')
      load()
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to update role', 'error')
    }
  }

  const handleResetPassword = async (user: User) => {
    if (!resetPw || resetPw.length < 4) {
      showToast('Password must be at least 4 characters', 'error')
      return
    }
    try {
      await api.updateUser(user.id, { password: resetPw })
      showToast(`Password reset for ${user.username}`, 'success')
      setResetId(null)
      setResetPw('')
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to reset password', 'error')
    }
  }

  const roleBadge = (role: string) => {
    const c = role === 'admin' ? colors.danger : role === 'user' ? colors.primary : colors.textMuted
    return (
      <span style={{
        display: 'inline-block',
        padding: '2px 8px',
        fontSize: 'clamp(9px, 0.9vw, 10px)',
        letterSpacing: '0.15em',
        fontFamily: "'Orbitron', sans-serif",
        border: `1px solid ${c}44`,
        color: c,
        background: `${c}0a`,
      }}>
        {role.toUpperCase()}
      </span>
    )
  }

  const roleOptions = [
    { value: 'admin', label: 'admin' },
    { value: 'user', label: 'user' },
    { value: 'readonly', label: 'readonly' },
  ]

  return (
    <div style={{ padding: 'clamp(16px, 4vw, 32px)', maxWidth: '1400px', animation: 'pp-fadein 0.4s ease both' }}>
      {deleteUser && (
        <ConfirmModal
          title="Delete User"
          message={`Delete user "${deleteUser.username}"?`}
          confirmLabel="Delete"
          variant="danger"
          onConfirm={() => {
            const user = deleteUser
            setDeleteUser(null)
            handleDelete(user)
          }}
          onCancel={() => setDeleteUser(null)}
        />
      )}

      <PageHeader>Users</PageHeader>

      {/* User list */}
      <Card style={{ padding: '20px 22px', marginBottom: '28px' }}>
        {loading ? (
          <div style={{ color: colors.textMuted, fontSize: '12px' }}>Loading users...</div>
        ) : loadError ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
            <div>
              <div style={{ color: colors.danger, fontSize: '12px', marginBottom: '4px' }}>Failed to load users</div>
              <div style={{ color: colors.textMuted, fontSize: '11px' }}>{loadError}</div>
            </div>
            <Button onClick={() => { setLoading(true); load() }}>Retry</Button>
          </div>
        ) : users.length === 0 ? (
          <div style={{ color: colors.textMuted, fontSize: '12px' }}>No users found.</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', fontFamily: "'Electrolize', monospace" }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${colors.border}` }}>
                  {['USER', 'ROLE', 'CREATED', 'PASSWORD', ''].map((h, i) => (
                    <th key={i} style={{
                      textAlign: i === 4 ? 'right' : 'left',
                      padding: '8px 10px',
                      color: colors.textMuted,
                      fontSize: 'clamp(9px, 0.9vw, 10px)',
                      letterSpacing: '0.2em',
                      fontFamily: "'Orbitron', sans-serif",
                      fontWeight: 500,
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} style={{ borderBottom: `1px solid ${colors.border}22` }}>
                    <td style={{ padding: '10px 10px', color: colors.text }}>{u.username}</td>
                    <td style={{ padding: '10px 10px', position: 'relative', zIndex: 20 }}>
                      <div style={{ width: '140px', position: 'relative', zIndex: 20 }}>
                        <Dropdown
                          value={u.role}
                          onChange={value => handleRoleChange(u, value)}
                          options={roleOptions}
                        />
                      </div>
                    </td>
                    <td style={{ padding: '10px 10px', color: colors.textMuted, fontSize: '11px' }}>
                      {u.created?.replace('T', ' ').slice(0, 16) ?? '—'}
                    </td>
                    <td style={{ padding: '10px 10px' }}>
                      {resetId === u.id ? (
                        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                          <input
                            type="password"
                            value={resetPw}
                            onChange={e => setResetPw(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter') handleResetPassword(u); if (e.key === 'Escape') { setResetId(null); setResetPw('') } }}
                            placeholder="new password"
                            autoFocus
                            style={{ ...inputStyle, width: '120px', minHeight: '36px', padding: '6px 8px', fontSize: '11px', lineHeight: '16px' }}
                          />
                          <Button size="sm" style={{ minHeight: '36px' }} onClick={() => handleResetPassword(u)}>Set</Button>
                          <Button variant="ghost" size="sm" style={{ minHeight: '36px' }} onClick={() => { setResetId(null); setResetPw('') }}>✕</Button>
                        </div>
                      ) : (
                        <Button variant="ghost" size="sm" style={{ minHeight: '39px', minWidth: '60px' }} onClick={() => { setResetId(u.id); setResetPw('') }}>
                          Reset
                        </Button>
                      )}
                    </td>
                    <td style={{ padding: '10px 10px', textAlign: 'right' }}>
                      <Button variant="danger" size="sm" style={{ minHeight: '39px', minWidth: '60px' }} onClick={() => setDeleteUser(u)}>
                        Delete
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Create user */}
      <SectionHeader>Add User</SectionHeader>
      <Card style={{ padding: '20px 22px' }}>
        <form onSubmit={handleCreate} style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ flex: '1 1 140px', minWidth: '120px' }}>
            <div style={labelStyle}>Username</div>
            <input
              value={newUser.username}
              onChange={e => setNewUser(p => ({ ...p, username: e.target.value }))}
              placeholder="username"
              style={inputStyle}
            />
          </div>
          <div style={{ flex: '1 1 140px', minWidth: '120px' }}>
            <div style={labelStyle}>Password</div>
            <input
              type="password"
              value={newUser.password}
              onChange={e => setNewUser(p => ({ ...p, password: e.target.value }))}
              placeholder="password"
              style={inputStyle}
            />
          </div>
          <div style={{ flex: '0 0 120px' }}>
            <div style={labelStyle}>Role</div>
            <Dropdown
              value={newUser.role}
              onChange={value => setNewUser(p => ({ ...p, role: value }))}
              options={roleOptions}
            />
          </div>
          <Button type="submit" style={{ minHeight: '39px' }} disabled={!newUser.username.trim() || !newUser.password}>
            Add User
          </Button>
        </form>
      </Card>

      {/* Role legend */}
      <div style={{ marginTop: '24px', display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
        {[
          { role: 'admin', desc: 'Full access — manage VMs, schedules, settings, users' },
          { role: 'user', desc: 'View + trigger jobs — no delete, no settings, no users' },
          { role: 'readonly', desc: 'View only — dashboard, VM details, schedules' },
        ].map(r => (
          <div key={r.role} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {roleBadge(r.role)}
            <span style={{ fontSize: '10px', color: colors.textDim, fontFamily: "'Electrolize', monospace" }}>
              {r.desc}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
