export function fmtDate(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

export function fmtNumber(value: number | null | undefined) {
  const number = Number(value ?? 0)
  return Number.isFinite(number) ? number.toLocaleString('zh-CN') : '0'
}

export function fmtScore(value: number | null | undefined) {
  const number = Number(value ?? 0)
  return Number.isFinite(number) ? number.toFixed(2) : '0.00'
}

export function severityTone(severity: string | null | undefined) {
  const value = String(severity || '').toLowerCase()
  if (value === 'critical') return 'red'
  if (value === 'high') return 'navy'
  if (value === 'medium') return 'cyan'
  if (value === 'low' || value === 'info') return 'green'
  return 'blue'
}

export function statusTone(status: string | null | undefined) {
  const value = String(status || '').toLowerCase()
  if (['failed', 'error', 'rejected', 'false_positive'].includes(value)) return 'red'
  if (['running', 'queued', 'investigating', 'candidate', 'needs_review'].includes(value)) return 'orange'
  if (['completed', 'resolved', 'closed', 'validated', 'confirmed', 'fixed', 'ok'].includes(value)) return 'green'
  if (['open', 'triaged'].includes(value)) return 'purple'
  return 'blue'
}

export function shortId(value: string | null | undefined) {
  return value ? value.slice(0, 8) : '—'
}
