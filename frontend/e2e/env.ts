export function requireEnv(name: string): string {
  const value = process.env[name]?.trim()
  if (!value) {
    throw new Error(`Fehlende Umgebungsvariable: ${name}`)
  }
  return value
}

export function getE2eCredentials() {
  return {
    username: requireEnv('PP_E2E_USERNAME'),
    password: requireEnv('PP_E2E_PASSWORD'),
  }
}

export function getHttpsEnableConfig() {
  return {
    enabled: process.env.PP_E2E_RUN_SSL_ENABLE === '1',
    httpBaseUrl: process.env.PP_E2E_HTTP_BASE_URL?.trim() || '',
    httpsBaseUrl: process.env.PP_E2E_HTTPS_BASE_URL?.trim() || '',
  }
}

export function getLinuxAgentId() {
  return process.env.PP_E2E_LINUX_AGENT_ID?.trim() || 'Test2'
}

export function getHaAgentId() {
  return process.env.PP_E2E_HA_AGENT_ID?.trim() || ''
}
