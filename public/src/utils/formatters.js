export function normalizeText(value) {
  return String(value || '').trim()
}

export function normalizeIpAddress(value) {
  let normalized = normalizeText(value).toLowerCase()
  if (normalized.startsWith('::ffff:')) normalized = normalized.slice(7)
  if (normalized.startsWith('[') && normalized.includes(']')) {
    normalized = normalized.slice(1, normalized.indexOf(']'))
  }
  return normalized.split('%', 1)[0]
}

export function normalizeMacAddress(value) {
  return normalizeText(value).toUpperCase().replace(/[^0-9A-F]/g, '')
}

export function formatLimit(value) {
  return value === null || value === undefined ? 'Unlimited' : formatBytes(value)
}

export function formatDeviceCount(value) {
  const count = Math.max(0, Number(value) || 0)
  return `${count}${count === 1 ? ' device' : ' devices'}`
}

export function formatTime(date) {
  const diff = Math.floor((new Date() - date) / 1000)
  if (diff < 60) return 'Just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function formatBytes(bytes) {
  let value = Number(bytes || 0)
  if (!Number.isFinite(value) || value < 0) value = 0
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return unitIndex === 0
    ? `${Math.round(value)} ${units[unitIndex]}`
    : `${value.toFixed(1)} ${units[unitIndex]}`
}

export function publicErrorMessage(statusCode) {
  switch (statusCode) {
    case 400:
    case 422:
      return 'The request was invalid. Please check the details and try again.'
    case 401:
      return 'Invalid username or password.'
    case 403:
      return 'This request is not allowed.'
    case 404:
      return 'The requested voucher or device was not found.'
    case 408:
    case 504:
      return 'The request timed out. Please try again.'
    case 429:
      return 'Too many requests. Please wait and try again.'
    case 500:
    case 502:
    case 503:
      return 'The router service is temporarily unavailable. Please try again later.'
    default:
      return 'The request could not be completed. Please try again.'
  }
}
