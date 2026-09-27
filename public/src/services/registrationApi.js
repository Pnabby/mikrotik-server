const API_URL = String(import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

export class RegistrationApiError extends Error {
  constructor(status, detail = '', code = '', fieldErrors = {}) {
    super(`Registration API request failed with status ${status}`)
    this.name = 'RegistrationApiError'
    this.status = status
    this.detail = detail
    this.code = code
    this.fieldErrors = fieldErrors
  }
}

async function request(path, body) {
  const response = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const responseBody = await response.json().catch(() => ({}))
    throw new RegistrationApiError(
      response.status,
      responseBody.detail || '',
      responseBody.code || '',
      responseBody.field_errors || {},
    )
  }
  return response.json()
}

export function startRegistration(details) {
  return request('/api/registration/start', details)
}

export async function getUsernameAvailability(username, signal) {
  const query = new URLSearchParams({ username })
  const response = await fetch(`${API_URL}/api/registration/username-availability?${query}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) {
    const responseBody = await response.json().catch(() => ({}))
    throw new RegistrationApiError(
      response.status,
      responseBody.detail || '',
      responseBody.code || '',
      responseBody.field_errors || {},
    )
  }
  return response.json()
}

export async function getRegistrationRouterReadiness(routerId, username, signal) {
  const query = new URLSearchParams({ router_id: routerId, username })
  const response = await fetch(`${API_URL}/api/registration/router-readiness?${query}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) {
    const responseBody = await response.json().catch(() => ({}))
    throw new RegistrationApiError(
      response.status,
      responseBody.detail || '',
      responseBody.code || '',
      responseBody.field_errors || {},
    )
  }
  return response.json()
}

export function completeRegistration(challengeId, details, code) {
  return request('/api/registration/complete', {
    ...details,
    challenge_id: challengeId,
    code,
  })
}
