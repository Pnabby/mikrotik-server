export const DURATION_UNITS = {
  hours: 60 * 60,
  days: 24 * 60 * 60,
  weeks: 7 * 24 * 60 * 60,
  months: 30 * 24 * 60 * 60,
}

const FORM_FIELDS = {
  displayName: 'display_name', description: 'description', amount: 'amount', currency: 'currency',
  durationValue: 'duration_seconds', durationUnit: 'duration_seconds', dataLimitGb: 'data_limit_bytes',
  deviceLimit: 'device_limit', downloadSpeed: 'download_speed', isPromotional: 'is_promotional',
  isVisible: 'is_visible', groupId: 'group_id',
}

const optionalText = (value) => String(value || '').trim().replace(/\s+/g, ' ') || null

export function profileDetailsFromForm(form, profile) {
  return {
    display_name: optionalText(form.displayName) || '',
    description: optionalText(form.description),
    amount: form.amount === '' ? null : Number(form.amount).toFixed(2),
    currency: form.currency.toUpperCase(),
    duration_seconds: form.durationValue === ''
      ? null : Math.round(Number(form.durationValue) * DURATION_UNITS[form.durationUnit]),
    data_limit_bytes: form.dataLimitGb === ''
      ? null : Math.round(Number(form.dataLimitGb) * 1024 ** 3),
    device_limit: form.applyRouterSettings
      ? (form.unlimitedSharedUsers ? null : Number(form.sharedUsers))
      : form.deviceLimit === '' ? null : Number(form.deviceLimit),
    download_speed: optionalText(form.downloadSpeed),
    is_promotional: profile.is_registration_profile ? false : form.isPromotional,
    is_visible: profile.is_registration_profile ? false : form.isVisible,
    ...(!profile.bulk_mode ? { group_id: form.groupId || null } : {}),
  }
}

export function changedProfileDetails(initialForm, form, profile, editedFields = []) {
  const initial = profileDetailsFromForm(initialForm, profile)
  const current = profileDetailsFromForm(form, profile)
  const mixed = new Set(profile.mixed_fields || [])
  const edited = new Set(editedFields.map((field) => FORM_FIELDS[field]))
  return Object.fromEntries(Object.entries(current).filter(([key, value]) => (
    !Object.is(value, initial[key]) || (mixed.has(key) && edited.has(key))
  )))
}

export function profileSaveRequest(profile, payload, changes) {
  if (!profile.is_configured) return { method: 'PUT', payload }
  if (!payload.router_settings) return { method: 'PATCH', payload: changes }

  // Each hostel keeps its commercial terms unless the admin edits them.
  const existing = Object.fromEntries(Object.values(FORM_FIELDS).map((key) => [key, profile[key]]))
  return {
    method: 'PUT',
    payload: {
      ...existing, ...changes,
      router_settings: payload.router_settings,
      source_router_id: payload.source_router_id,
    },
  }
}

export function mergeProfileDetails(profile, saved, changes) {
  const merged = { ...profile, ...saved }
  // A null database label can represent a speed originally read from RouterOS.
  if (saved.download_speed === null && !Object.hasOwn(changes, 'download_speed')) {
    merged.download_speed = profile.download_speed
  }
  return merged
}
