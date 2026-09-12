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
  if (response.status === 204) return null
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

export function getDashboard(routerId = null) {
  const query = routerId ? `?router_id=${encodeURIComponent(routerId)}` : ''
  return request(`/api/admin/dashboard${query}`)
}

export function getAccessPoints(routerId) {
  return request(`/api/admin/dashboard/access-points?router_id=${encodeURIComponent(routerId)}`)
}

export function getTransactions(filters = {}) {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) query.set(key, value)
  })
  return request(`/api/admin/dashboard/transactions${query.size ? `?${query}` : ''}`)
}

export function getCustomersAndDevices(filters = {}) {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) query.set(key, value)
  })
  return request(`/api/admin/dashboard/customers${query.size ? `?${query}` : ''}`)
}

export function createHostel(hostel) {
  return request('/api/admin/hostels', {
    method: 'POST',
    body: JSON.stringify(hostel),
  })
}

export function updateHostel(routerId, hostel) {
  return request(`/api/admin/hostels/${encodeURIComponent(routerId)}`, {
    method: 'PUT',
    body: JSON.stringify(hostel),
  })
}

export function forceHostelIpCloudUpdate(routerId) {
  return request(
    `/api/admin/hostels/${encodeURIComponent(routerId)}/ip-cloud/force-update`,
    { method: 'POST' },
  )
}

export function listHostelProfiles(routerId) {
  return request(`/api/admin/hostels/${encodeURIComponent(routerId)}/profiles`)
}

export function listPlanGroups(routerId) {
  return request(`/api/admin/hostels/${encodeURIComponent(routerId)}/plan-groups`)
}

export function listAllHostelPlanGroups() {
  return request('/api/admin/plan-groups')
}

export function createAllHostelPlanGroup(group) {
  return request('/api/admin/plan-groups', {
    method: 'POST',
    body: JSON.stringify(group),
  })
}

export function updateAllHostelPlanGroup(groupKey, group) {
  return request(`/api/admin/plan-groups/${encodeURIComponent(groupKey)}`, {
    method: 'PUT',
    body: JSON.stringify(group),
  })
}

export function deleteAllHostelPlanGroup(groupKey) {
  return request(`/api/admin/plan-groups/${encodeURIComponent(groupKey)}`, {
    method: 'DELETE',
  })
}

export function createPlanGroup(routerId, group) {
  return request(`/api/admin/hostels/${encodeURIComponent(routerId)}/plan-groups`, {
    method: 'POST',
    body: JSON.stringify(group),
  })
}

export function updatePlanGroup(routerId, groupId, group) {
  return request(`/api/admin/hostels/${encodeURIComponent(routerId)}/plan-groups/${encodeURIComponent(groupId)}`, {
    method: 'PUT',
    body: JSON.stringify(group),
  })
}

export function deletePlanGroup(routerId, groupId) {
  return request(`/api/admin/hostels/${encodeURIComponent(routerId)}/plan-groups/${encodeURIComponent(groupId)}`, {
    method: 'DELETE',
  })
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

export function deleteHostelProfileConfiguration(routerId, mikrotikProfile) {
  return request(
    `/api/admin/hostels/${encodeURIComponent(routerId)}/profiles/${encodeURIComponent(mikrotikProfile)}`,
    { method: 'DELETE' },
  )
}

export function getSupportSettings() {
  return request('/api/admin/support')
}

export function saveSupportSettings(settings) {
  return request('/api/admin/support', {
    method: 'PUT',
    body: JSON.stringify(settings),
  })
}

export function sendBroadcast(subject, message, routerId = null) {
  return request('/api/admin/dashboard/broadcast', {
    method: 'POST',
    body: JSON.stringify({ subject, message, router_id: routerId || null }),
  })
}
