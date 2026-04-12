/** Format seconds as relative time: "5m ago", "2h ago" */
export function fmtAgo(secs: number | null): string {
  if (secs === null) return '—'
  if (secs < 0) return 'just now'
  if (secs < 60) return `${Math.floor(secs)}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m ago`
  return `${Math.floor(secs / 86400)}d ${Math.floor((secs % 86400) / 3600)}h ago`
}

/** Format seconds as short relative: "5m", "2h" */
export function fmtAgoShort(secs: number | null): string {
  if (secs === null) return '—'
  if (secs < 60) return `${Math.floor(secs)}s`
  if (secs < 3600) return `${Math.floor(secs / 60)}m`
  return `${Math.floor(secs / 3600)}h`
}

/** Format uptime seconds as "5d 3h" or "2h 15m" */
export function fmtUptime(secs: number | null): string {
  if (secs === null) return '—'
  const d = Math.floor(secs / 86400)
  const h = Math.floor((secs % 86400) / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  return `${h}h ${m}m`
}

/** Format bytes as human-readable size: "12.3 GB", "512 MB" */
export function fmtBytes(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

/** Describe a cron expression in human-readable form */
export function describeCron(expr: string): string {
  const parts = expr.trim().split(/\s+/)
  if (parts.length !== 5) return ''
  const [min, hour, dom, mon, dow] = parts

  const dowNames: Record<string, string> = {
    '0': 'Sundays', '1': 'Mondays', '2': 'Tuesdays', '3': 'Wednesdays',
    '4': 'Thursdays', '5': 'Fridays', '6': 'Saturdays', '7': 'Sundays',
  }

  const fmtTime = (h: string, m: string) => {
    const hh = h.padStart(2, '0')
    const mm = m.padStart(2, '0')
    return `${hh}:${mm}`
  }

  // Every N minutes
  if (min.startsWith('*/') && hour === '*' && dom === '*' && mon === '*' && dow === '*') {
    return `Every ${min.slice(2)} minutes`
  }

  // Every N hours
  if (hour.startsWith('*/') && dom === '*' && mon === '*' && dow === '*') {
    return `Every ${hour.slice(2)} hours`
  }

  // Specific time, every day
  if (!min.includes('*') && !min.includes('/') && !hour.includes('*') && !hour.includes('/') && dom === '*' && mon === '*' && dow === '*') {
    return `Daily at ${fmtTime(hour, min)}`
  }

  // Specific time, specific days of week
  if (!min.includes('*') && !hour.includes('*') && dom === '*' && mon === '*' && dow !== '*') {
    const days = dow.split(',').map(d => {
      if (d.includes('-')) {
        const [a, b] = d.split('-')
        return `${dowNames[a] || a}–${dowNames[b] || b}`
      }
      return dowNames[d] || d
    }).join(', ')
    return `${days} at ${fmtTime(hour, min)}`
  }

  // Specific day of month
  if (!min.includes('*') && !hour.includes('*') && dom !== '*' && mon === '*' && dow === '*') {
    return `Day ${dom} of each month at ${fmtTime(hour, min)}`
  }

  return ''
}
