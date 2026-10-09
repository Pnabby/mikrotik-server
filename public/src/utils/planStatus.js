export function getPlanStatus(currentPlan, networkStatus, networkPhase, now = Date.now()) {
  if (!currentPlan) return 'inactive'
  if (networkPhase === 'loading') return 'checking'
  if (networkPhase !== 'ready' || typeof networkStatus?.disabled !== 'boolean') return 'unavailable'

  // RouterOS is authoritative: a stored subscription cannot enable a disabled user.
  if (networkStatus.disabled) return 'exhausted'

  const remaining = networkStatus.total_data_left_bytes
  const expiry = networkStatus.expiry_date || currentPlan.expires_at
  const normalizedExpiry = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(expiry || '')
    ? `${expiry.replace(' ', 'T')}Z`
    : expiry
  const expiresAt = normalizedExpiry ? new Date(normalizedExpiry).getTime() : NaN
  if ((remaining !== null && remaining !== undefined && Number(remaining) <= 0)
    || (Number.isFinite(expiresAt) && expiresAt <= now)) return 'exhausted'

  return 'active'
}
