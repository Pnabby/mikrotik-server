const API_URL = String(import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(status) {
    super(`API request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) throw new ApiError(response.status)
  return response.json()
}

export function getStatusSession(search = '') {
  return request(`/api/status-session${search}`)
}

export function getRouters() {
  return request('/api/routers')
}

export function getHotspotStatus(routerId, username) {
  return request(
    `/api/routers/${encodeURIComponent(routerId)}/hotspot/users/${encodeURIComponent(username)}/status`,
  )
}

export function lookupHotspotUser(routerId, username, password) {
  return request(`/api/routers/${encodeURIComponent(routerId)}/hotspot/user-lookup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function logoutHotspotDevice(routerId, username, device) {
  const path =
    `/api/routers/${encodeURIComponent(routerId)}/hotspot/users/${encodeURIComponent(username)}` +
    `/devices/${encodeURIComponent(device.session_id || 'lookup')}/logout`
  const query = new URLSearchParams()
  if (device.mac_address) query.set('mac_address', device.mac_address)
  if (device.ip_address) query.set('ip_address', device.ip_address)
  const suffix = query.size ? `?${query}` : ''
  return request(`${path}${suffix}`, { method: 'POST' })
}
