const BASE = '/api'
const STORAGE_KEY = 'pp_admin_key'

export type Role = 'admin' | 'user' | 'readonly'

export const auth = {
  getKey: () => sessionStorage.getItem(STORAGE_KEY) ?? '',
  setKey: (k: string) => sessionStorage.setItem(STORAGE_KEY, k),
  getToken: () => sessionStorage.getItem('pp_token') ?? '',
  getRole: () => {
    const role = sessionStorage.getItem('pp_role')
    if (role) return role as Role
    // Legacy: if admin key is set but no role, it's an admin
    if (sessionStorage.getItem(STORAGE_KEY)) return 'admin' as Role
    return 'readonly' as Role
  },
  getUsername: () => sessionStorage.getItem('pp_username') ?? '',
  setSession: (token: string, role: string, username: string) => {
    sessionStorage.setItem('pp_token', token)
    sessionStorage.setItem('pp_role', role)
    sessionStorage.setItem('pp_username', username)
  },
  clear: () => {
    sessionStorage.removeItem(STORAGE_KEY)
    sessionStorage.removeItem('pp_token')
    sessionStorage.removeItem('pp_role')
    sessionStorage.removeItem('pp_username')
  },
  isSet: () => !!(sessionStorage.getItem(STORAGE_KEY) || sessionStorage.getItem('pp_token')),
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body) headers['Content-Type'] = 'application/json'
  // Session token takes priority over legacy admin key
  const token = auth.getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  } else {
    const key = auth.getKey()
    if (key) headers['x-admin-key'] = key
  }

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) {
    auth.clear()
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `${method} ${path} → ${res.status}`)
  }
  return res.json() as Promise<T>
}

export interface Agent {
  id: string
  hostname: string
  ip: string | null
  os_pretty: string | null
  kernel: string | null
  arch: string | null
  package_manager: string | null
  reboot_required: number
  pending_count: number
  last_seen: string | null
  seconds_ago: number | null
  tags: string | null
  uptime_seconds: number | null
  last_job_type: string | null
  last_job_status: string | null
  last_job_finished: string | null
  protocol: string | null
  config_review_required: number
  config_review_note: string | null
}

export interface Package {
  id: number
  agent_id: string
  name: string
  current_ver: string | null
  new_ver: string | null
}

export interface Job {
  id: number
  agent_id: string
  type: string
  status: string
  created: string
  started: string | null
  finished: string | null
  output: string | null
  params: string | null
}

export interface Schedule {
  id: number
  name: string
  cron: string
  action: string
  target: string
  enabled: number
  last_run: string | null
  next_run: string | null
}

export interface Settings {
  telegram_token: string
  telegram_chat_id: string
  email_enabled: string
  smtp_host: string
  smtp_port: string
  smtp_security: string
  smtp_user: string
  smtp_password: string
  smtp_to: string
  notify_offline: string
  notify_offline_minutes: string
  notify_patches: string
  notify_failures: string
  telegram_enabled: string
  telegram_notify_offline: string
  telegram_notify_patches: string
  telegram_notify_failures: string
  telegram_notify_success: string
  server_port: string
  agent_port: string
  agent_ssl: string
  agent_url: string
  ssl_certfile: string
  ssl_keyfile: string
  ssl_enabled: boolean
  ui_audio_enabled: string
  ui_audio_volume: string
  ui_login_animation_enabled: string
  ui_login_background_animation_enabled: string
  ui_login_background_opacity: string
}

export interface User {
  id: number
  username: string
  role: Role
  created: string
}

export interface DeployBootstrap {
  ca_pem_b64: string
}

export const api = {
  // Auth
  login: (username: string, password: string) =>
    req<{ token: string; role: string; username: string }>('POST', '/auth/login', { username, password }),

  logout: () =>
    req<{ status: string }>('POST', '/auth/logout'),

  me: () =>
    req<{ username: string; role: string }>('GET', '/auth/me'),

  // Users
  users: () =>
    req<{ users: User[] }>('GET', '/users'),

  createUser: (data: { username: string; password: string; role: string }) =>
    req<{ status: string }>('POST', '/users', data),

  updateUser: (id: number, data: { role?: string; password?: string }) =>
    req<{ status: string }>('PATCH', `/users/${id}`, data),

  deleteUser: (id: number) =>
    req<{ status: string }>('DELETE', `/users/${id}`),

  // Dashboard
  dashboard: () =>
    req<{ agents: Agent[]; stats: { online: number; total: number; reboot_needed: number; total_pending: number } }>('GET', '/dashboard'),

  agent: (id: string) =>
    req<{ agent: Agent; packages: Package[]; jobs: Job[] }>('GET', `/agents/${id}`),

  createJob: (agentId: string, type: string, params?: Record<string, unknown>) =>
    req('POST', `/agents/${agentId}/jobs`, { type, params: params ?? {} }),

  cancelJob: (agentId: string, jobId: number) =>
    req('POST', `/agents/${agentId}/jobs/${jobId}/cancel`),

  cancelPendingJobs: (agentId: string) =>
    req<{ cancelled: number }>('POST', `/agents/${agentId}/jobs/cancel-pending`),

  deleteAgent: (id: string) =>
    req('DELETE', `/agents/${id}`),

  acknowledgeConfigReview: (id: string) =>
    req<{ status: string }>('POST', `/agents/${id}/config-review/ack`),

  // Schedules
  schedules: () =>
    req<{ schedules: Schedule[]; agents: { id: string; hostname: string }[] }>('GET', '/schedules'),

  createSchedule: (data: { name: string; cron: string; action: string; target: string }) =>
    req('POST', '/schedules', data),

  updateSchedule: (id: number, data: { name: string; cron: string; action: string; target: string }) =>
    req('PUT', `/schedules/${id}`, data),

  runScheduleNow: (id: number) =>
    req('POST', `/schedules/${id}/run`),

  toggleSchedule: (id: number, enabled: boolean) =>
    req('PATCH', `/schedules/${id}`, { enabled }),

  deleteSchedule: (id: number) =>
    req('DELETE', `/schedules/${id}`),

  // Settings
  settings: () =>
    req<Settings>('GET', '/settings'),

  saveSettings: (data: Partial<Settings>) =>
    req<{ status: string; restart_pending: boolean; new_port: string | null }>('POST', '/settings', data),

  testNotification: (channel: 'telegram' | 'email') =>
    req<{ status: string }>('POST', `/settings/test/${channel}`),

  // SSL
  sslInfo: () =>
    req<{ enabled: boolean; certfile: string; keyfile: string; info: { subject: string; expires: string; path: string } | null }>('GET', '/settings/ssl-info'),

  generateCert: (years: number = 3) =>
    req<{ status: string; certfile: string; keyfile: string; info: any; restart_pending: boolean }>('POST', '/settings/generate-cert', { years }),

  sslEnable: (certfile: string, keyfile: string) =>
    req<{ status: string; info: any; restart_pending: boolean }>('POST', '/settings/ssl-enable', { certfile, keyfile }),

  sslDisable: () =>
    req<{ status: string; restart_pending: boolean }>('POST', '/settings/ssl-disable'),

  deploySslToAgents: (retryBatch?: string) =>
    req<{ status: string; agent_count: number; batch_id: string }>('POST', '/settings/deploy-ssl', retryBatch ? { retry_batch: retryBatch } : undefined),

  deploySslStatus: (batchId: string) =>
    req<{ agents: Array<{ agent_id: string; hostname: string; status: string; phase: string; output: string; finished: string | null; online: boolean }>; total: number; total_online: number; completed: number }>('GET', `/settings/deploy-ssl/status?batch=${batchId}`),

  updateAgentsBatch: (retryBatch?: string) =>
    req<{ status: string; agent_count: number; batch_id: string }>('POST', '/agents/update-batch', retryBatch ? { retry_batch: retryBatch } : undefined),

  updateAgentsBatchStatus: (batchId: string) =>
    req<{ agents: Array<{ agent_id: string; hostname: string; status: string; phase: string; output: string; finished: string | null; online: boolean }>; total: number; total_online: number; completed: number }>('GET', `/agents/update-batch/status?batch=${batchId}`),

  setTags: (id: string, tags: string) =>
    req<{ status: string; tags: string }>('PATCH', `/agents/${id}/tags`, { tags }),

  registerKeyStatus: () =>
    req<{ active: boolean; key: string | null; expires_in: number }>('GET', '/register-key'),

  generateRegisterKey: () =>
    req<{ key: string; expires_in: number }>('POST', '/register-key'),

  deployBootstrap: () =>
    req<DeployBootstrap>('GET', '/deploy/bootstrap'),

  renameAgent: (id: string, newId: string) =>
    req<{ status: string; old_id: string; new_id: string }>('PATCH', `/agents/${id}/rename`, { new_id: newId }),
}
