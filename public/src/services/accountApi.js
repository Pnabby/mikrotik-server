const API_URL = String(import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

export class AccountApiError extends Error {
  constructor(status) {
    super(`Account request failed with status ${status}`)
    this.name = 'AccountApiError'
    this.status = status
  }
}

async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...options,
  })
  if (!response.ok) throw new AccountApiError(response.status)
  return response.json()
}

export function login(username, pin) {
  return request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, pin }),
  })
}

export function logout() {
  return request('/api/auth/logout', { method: 'POST' })
}

export function getAccount() {
  return request('/api/account')
}

export function getAccountHotspotStatus() {
  return request('/api/account/hotspot-status')
}

export function disconnectAccountDevice(device) {
  const path = `/api/account/devices/${encodeURIComponent(device.session_id)}/logout`
  const query = new URLSearchParams()
  if (device.mac_address) query.set('mac_address', device.mac_address)
  if (device.ip_address) query.set('ip_address', device.ip_address)
  return request(`${path}${query.size ? `?${query}` : ''}`, { method: 'POST' })
}
