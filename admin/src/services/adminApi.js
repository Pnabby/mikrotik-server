const API_URL = String(import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

export class AdminApiError extends Error {
  constructor(status) {
    super(`Admin request failed with status ${status}`)
    this.name = 'AdminApiError'
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
  if (!response.ok) throw new AdminApiError(response.status)
  return response.json()
}

export function login(username, password) {
  return request('/api/admin/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function getAdminSession() {
  return request('/api/admin/auth/session')
}

export function logout() {
  return request('/api/admin/auth/logout', { method: 'POST' })
}

export function listHostels() {
  return request('/api/admin/hostels')
}

export function listHostelProfiles(routerId) {
  return request(`/api/admin/hostels/${encodeURIComponent(routerId)}/profiles`)
}

export function saveHostelProfile(routerId, mikrotikProfile, profile) {
  return request(
    `/api/admin/hostels/${encodeURIComponent(routerId)}/profiles/${encodeURIComponent(mikrotikProfile)}`,
    {
      method: 'PUT',
      body: JSON.stringify(profile),
    },
  )
}
