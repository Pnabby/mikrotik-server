const USERNAME_PATTERN = /^[a-z0-9]{3,64}$/
const PHONE_PATTERN = /^\+[1-9][0-9]{7,14}$/
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function normalizePhoneNumber(value) {
  let phone = value.trim().replace(/[\s()-]/g, '')
  if (/^0[0-9]{9}$/.test(phone)) phone = `+233${phone.slice(1)}`
  else if (phone.startsWith('233')) phone = `+${phone}`
  return PHONE_PATTERN.test(phone) ? phone : ''
}

export function normalizeLoginIdentifier(value) {
  const identifier = value.trim().toLowerCase()
  return normalizePhoneNumber(identifier) || (USERNAME_PATTERN.test(identifier) ? identifier : '')
}

export function normalizeRecoveryIdentifier(value) {
  const identifier = value.trim().toLowerCase()
  return identifier.includes('@')
    ? (EMAIL_PATTERN.test(identifier) && identifier.length <= 320 ? identifier : '')
    : normalizePhoneNumber(identifier)
}
