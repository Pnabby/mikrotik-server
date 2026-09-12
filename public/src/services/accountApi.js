const API_URL = String(import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

export class AccountApiError extends Error {
  constructor(status, detail = '') {
    super(`Account request failed with status ${status}`)
    this.name = 'AccountApiError'
    this.status = status
    this.detail = detail
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
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new AccountApiError(response.status, body.detail || '')
  }
  return response.json()
}

export function login(username, pin, rememberMe = false) {
  return request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, pin, remember_me: rememberMe }),
  })
}

export function startPinReset(email) {
  return request('/api/auth/pin-reset/start', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export function completePinReset(challengeId, email, code, newPin, confirmation) {
  return request('/api/auth/pin-reset/complete', {
    method: 'POST',
    body: JSON.stringify({
      challenge_id: challengeId,
      email,
      code,
      new_pin: newPin,
      new_pin_confirmation: confirmation,
    }),
  })
}

export function startUsernameRecovery(email) {
  return request('/api/auth/username-recovery/start', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export function completeUsernameRecovery(challengeId, email, code) {
  return request('/api/auth/username-recovery/complete', {
    method: 'POST',
    body: JSON.stringify({ challenge_id: challengeId, email, code }),
  })
}

export function startAccountUnlock(username) {
  return request('/api/auth/account-unlock/start', {
    method: 'POST',
    body: JSON.stringify({ username }),
  })
}

export function completeAccountUnlock(challengeId, username, code) {
  return request('/api/auth/account-unlock/complete', {
    method: 'POST',
    body: JSON.stringify({ challenge_id: challengeId, username, code }),
  })
}

export function changePin(oldPin, newPin, confirmation) {
  return request('/api/account/change-pin', {
    method: 'POST',
    body: JSON.stringify({
      old_pin: oldPin,
      new_pin: newPin,
      new_pin_confirmation: confirmation,
    }),
  })
}

export function deleteAccount(pin) {
  return request('/api/account/delete', {
    method: 'POST',
    body: JSON.stringify({ pin }),
  })
}

export function transferHostel(destinationRouterId, pin) {
  return request('/api/account/transfer-hostel', {
    method: 'POST',
    body: JSON.stringify({ destination_router_id: destinationRouterId, pin }),
  })
}

export function listAvailableHostels() {
  return request('/api/routers')
}

export function logout() {
  return request('/api/auth/logout', { method: 'POST' })
}

export function getAccount() {
  return request('/api/account')
}

export function startPhoneVerification(phoneNumber) {
  return request('/api/account/phone-verification/start', {
    method: 'POST',
    body: JSON.stringify({ phone_number: phoneNumber }),
  })
}

export function completePhoneVerification(challengeId, phoneNumber, code) {
  return request('/api/account/phone-verification/complete', {
    method: 'POST',
    body: JSON.stringify({ challenge_id: challengeId, phone_number: phoneNumber, code }),
  })
}

export function getAccountHotspotStatus() {
  return request('/api/account/hotspot-status')
}

export function initializePlanPurchase(packageId) {
  return request('/api/payments/initialize', {
    method: 'POST',
    body: JSON.stringify({ package_id: packageId }),
  })
}

export function claimFreePlan(packageId) {
  return request('/api/payments/claim-free', {
    method: 'POST',
    body: JSON.stringify({ package_id: packageId }),
  })
}

export function retryFreePlanClaim(reference) {
  return request(`/api/payments/claim-free/${encodeURIComponent(reference)}/retry`, {
    method: 'POST',
  })
}

export function verifyPlanPurchase(reference) {
  return request(`/api/payments/${encodeURIComponent(reference)}/verify`, { method: 'POST' })
}

export function disconnectAccountDevice(device) {
  const path = `/api/account/devices/${encodeURIComponent(device.session_id)}/logout`
  const query = new URLSearchParams()
  if (device.mac_address) query.set('mac_address', device.mac_address)
  if (device.ip_address) query.set('ip_address', device.ip_address)
  return request(`${path}${query.size ? `?${query}` : ''}`, { method: 'POST' })
}
