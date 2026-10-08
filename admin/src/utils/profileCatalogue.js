const FIELDS = ['display_name', 'description', 'amount', 'currency', 'duration_seconds',
  'data_limit_bytes', 'device_limit', 'download_speed', 'is_promotional', 'is_visible',
  'is_configured', 'rate_limit', 'shared_users', 'session_timeout', 'idle_timeout', 'keepalive_timeout']

export function profilesAcrossHostels(profileLists, hostels = []) {
  const names = [...new Set(profileLists.flatMap((list) => list.map((p) => p.mikrotik_profile)))]
  return names.sort((a, b) => a.localeCompare(b)).map((name) => {
    const matches = profileLists.map((list) => list.find((p) => p.mikrotik_profile === name))
    const first = matches.find((p) => p?.available_on_router) || matches.find(Boolean)
    const present = matches.filter((p) => p?.available_on_router)
    const mixed = FIELDS.filter((key) => matches.some((p) => !p || !Object.is(p[key], first[key])))
    const shared = (key, fallback = null) => mixed.includes(key) ? fallback : first[key]
    return {
      ...first,
      package_id: null,
      ...Object.fromEntries(FIELDS.map((key) => [key, shared(key)])),
      currency: shared('currency', 'GHS'),
      is_promotional: shared('is_promotional', false),
      is_visible: matches.every((p) => p?.is_visible),
      is_configured: matches.every((p) => p?.is_configured),
      is_registration_profile: matches.some((p) => p?.is_registration_profile),
      available_on_router: present.length > 0,
      bulk_mode: true,
      configuration_consistent: mixed.length === 0,
      configured_hostels: matches.filter((p) => p?.is_configured).length,
      published_hostels: matches.filter((p) => p?.is_visible).length,
      available_hostels: present.length,
      hostel_count: profileLists.length,
      source_router_id: hostels[matches.indexOf(first)]?.router_id,
      mixed_fields: mixed,
      hostel_profiles: matches.map((p, index) => ({ ...p,
        router_id: hostels[index]?.router_id, hostel_name: hostels[index]?.name || `Hostel ${index + 1}`,
        available_on_router: Boolean(p?.available_on_router),
      })),
    }
  })
}
