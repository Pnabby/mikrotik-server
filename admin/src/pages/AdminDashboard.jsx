import { useEffect, useMemo, useState } from 'react'

import {
  AdminApiError,
  createHostel,
  deleteHostelProfileConfiguration,
  forceHostelIpCloudUpdate,
  getSupportSettings,
  listHostelProfiles,
  listHostels,
  logout,
  saveHostelProfile,
  saveSupportSettings,
  updateHostel,
} from '../services/adminApi'

const DURATION_UNITS = {
  hours: 60 * 60,
  days: 24 * 60 * 60,
  weeks: 7 * 24 * 60 * 60,
  months: 30 * 24 * 60 * 60,
}
const ALL_HOSTELS_ID = '__all_hostels__'
const BULK_PROFILE_FIELDS = [
  'display_name',
  'description',
  'amount',
  'currency',
  'duration_seconds',
  'data_limit_bytes',
  'device_limit',
  'download_speed',
  'is_promotional',
  'is_visible',
  'is_configured',
]

function Icon({ name }) {
  const paths = {
    grid: <><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" /></>,
    building: <><path d="M5 21V6.7c0-.7.4-1.3 1.1-1.5l7-2.1c1-.3 1.9.4 1.9 1.5V21M9 8h2M9 12h2M9 16h2M15 10h4v11M3 21h18" /></>,
    tag: <><path d="M20.4 13.4 13.5 20.3a2.3 2.3 0 0 1-3.2 0l-6.6-6.6a2.3 2.3 0 0 1-.7-1.6V5a2 2 0 0 1 2-2h7.1a2.3 2.3 0 0 1 1.6.7l6.7 6.5a2.3 2.3 0 0 1 0 3.2Z" /><circle cx="8" cy="8" r="1.3" /></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8" /></>,
    receipt: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Z" /><path d="M9 8h6M9 12h6M9 16h3" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
    refresh: <><path d="M20 6v5h-5M4 18v-5h5" /><path d="M6.1 9a7 7 0 0 1 11.5-2.6L20 11M4 13l2.4 4.6A7 7 0 0 0 17.9 15" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    close: <path d="M6 6l12 12M18 6 6 18" />,
    wifi: <><path d="M4.9 9.5a10.4 10.4 0 0 1 14.2 0M7.6 12.7a6.4 6.4 0 0 1 8.8 0M10.4 16a2.4 2.4 0 0 1 3.2 0" /><circle cx="12" cy="19" r="1" /></>,
    check: <path d="m5 12 4.2 4.2L19 6.5" />,
    alert: <><path d="M10.3 3.8 2.5 17.2A2 2 0 0 0 4.2 20h15.6a2 2 0 0 0 1.7-2.8L13.7 3.8a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></>,
    logout: <><path d="M10 17l5-5-5-5M15 12H3M15 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4" /></>,
  }
  return <svg aria-hidden="true" viewBox="0 0 24 24">{paths[name]}</svg>
}

function Brand() {
  return (
    <div className="dashboard-brand">
      <span><Icon name="wifi" /></span>
      <div><strong>Flint WiFi</strong><small>Admin console</small></div>
    </div>
  )
}

function formatMoney(amount, currency = 'GHS') {
  if (amount === null || amount === undefined) return 'Not priced'
  return new Intl.NumberFormat('en-GH', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(Number(amount))
}

function formatDuration(seconds) {
  if (!seconds) return 'Not set'
  const days = seconds / DURATION_UNITS.days
  if (Number.isInteger(days) && days >= 1) return `${days} ${days === 1 ? 'day' : 'days'}`
  const hours = seconds / DURATION_UNITS.hours
  return `${hours} ${hours === 1 ? 'hour' : 'hours'}`
}

function durationParts(seconds, sessionTimeout) {
  if (seconds) {
    for (const candidate of ['months', 'weeks', 'days', 'hours']) {
      if (seconds % DURATION_UNITS[candidate] === 0) {
        return { value: seconds / DURATION_UNITS[candidate], unit: candidate }
      }
    }
    return { value: seconds / DURATION_UNITS.hours, unit: 'hours' }
  }
  const match = String(sessionTimeout || '').match(/^(\d+)([hdw])$/i)
  if (match) {
    return {
      value: Number(match[1]),
      unit: { h: 'hours', d: 'days', w: 'weeks' }[match[2].toLowerCase()],
    }
  }
  return { value: '', unit: 'days' }
}

function titleFromProfile(name) {
  return name
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

function statusFor(profile) {
  if (profile.is_registration_profile) return { label: 'System', className: 'system' }
  if (!profile.available_on_router) return { label: 'Missing on router', className: 'missing' }
  if (profile.bulk_mode && !profile.configuration_consistent) return { label: 'Mixed settings', className: 'mixed' }
  if (profile.is_visible) return { label: 'Published', className: 'published' }
  if (profile.is_configured) return { label: 'Draft', className: 'draft' }
  return { label: 'Not configured', className: 'unconfigured' }
}

function profilesCommonToAll(profileLists) {
  if (!profileLists.length) return []

  return profileLists[0]
    .filter((profile) => profile.available_on_router)
    .map((firstProfile) => {
      const profileName = firstProfile.mikrotik_profile.toLocaleLowerCase()
      const matches = profileLists.map((profiles) => profiles.find((profile) => (
        profile.available_on_router
        && profile.mikrotik_profile.toLocaleLowerCase() === profileName
      )))
      if (matches.some((profile) => !profile)) return null

      const sharedValue = (key, fallback = null) => (
        matches.every((profile) => Object.is(profile[key], matches[0][key]))
          ? matches[0][key]
          : fallback
      )
      const mixedFields = BULK_PROFILE_FIELDS.filter((key) => (
        !matches.every((profile) => Object.is(profile[key], matches[0][key]))
      ))

      return {
        ...firstProfile,
        package_id: null,
        display_name: sharedValue('display_name'),
        description: sharedValue('description'),
        amount: sharedValue('amount'),
        currency: sharedValue('currency', 'GHS'),
        duration_seconds: sharedValue('duration_seconds'),
        data_limit_bytes: sharedValue('data_limit_bytes'),
        device_limit: sharedValue('device_limit'),
        download_speed: sharedValue('download_speed'),
        is_promotional: sharedValue('is_promotional', false),
        is_configured: matches.every((profile) => profile.is_configured),
        is_visible: matches.every((profile) => profile.is_visible),
        is_registration_profile: matches.every((profile) => profile.is_registration_profile),
        rate_limit: sharedValue('rate_limit'),
        shared_users: sharedValue('shared_users'),
        session_timeout: sharedValue('session_timeout'),
        idle_timeout: sharedValue('idle_timeout'),
        address_pool: sharedValue('address_pool'),
        available_on_router: true,
        bulk_mode: true,
        configuration_consistent: mixedFields.length === 0,
        configured_hostels: matches.filter((profile) => profile.is_configured).length,
        published_hostels: matches.filter((profile) => profile.is_visible).length,
        hostel_count: matches.length,
        mixed_fields: mixedFields,
      }
    })
    .filter(Boolean)
}

function withoutProfileConfiguration(profile) {
  return {
    ...profile,
    package_id: null,
    display_name: null,
    description: null,
    amount: null,
    currency: 'GHS',
    duration_seconds: null,
    data_limit_bytes: null,
    device_limit: null,
    download_speed: null,
    is_promotional: false,
    is_configured: false,
    is_visible: false,
    configuration_consistent: true,
    configured_hostels: 0,
    published_hostels: 0,
    mixed_fields: [],
  }
}

function ProfileEditor({ hostel, profile, onClose, onDelete, onSave }) {
  const mixedFields = new Set(profile.mixed_fields || [])
  const startingDuration = mixedFields.has('duration_seconds')
    ? { value: '', unit: 'days' }
    : durationParts(
      profile.duration_seconds,
      profile.is_configured ? null : profile.session_timeout,
    )
  const [form, setForm] = useState({
    displayName: mixedFields.has('display_name') ? '' : profile.display_name || titleFromProfile(profile.mikrotik_profile),
    description: mixedFields.has('description') ? '' : profile.description || '',
    amount: mixedFields.has('amount') ? '' : profile.amount ?? '',
    currency: profile.currency || 'GHS',
    durationValue: startingDuration.value,
    durationUnit: startingDuration.unit,
    dataLimitGb: !mixedFields.has('data_limit_bytes') && profile.data_limit_bytes ? profile.data_limit_bytes / 1024 ** 3 : '',
    deviceLimit: mixedFields.has('device_limit') ? '' : profile.device_limit || '',
    downloadSpeed: mixedFields.has('download_speed') ? '' : profile.download_speed || '',
    isPromotional: mixedFields.has('is_promotional') ? false : profile.is_promotional || false,
    isVisible: profile.is_registration_profile || mixedFields.has('is_visible') ? false : profile.is_visible,
  })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const canDelete = profile.is_configured || (profile.bulk_mode && profile.configured_hostels > 0)

  function change(event) {
    const { name, value, checked, type } = event.target
    setForm((current) => ({ ...current, [name]: type === 'checkbox' ? checked : value }))
    setError('')
  }

  async function submit(event) {
    event.preventDefault()
    if (!form.displayName.trim()) {
      setError('Enter the name customers should see.')
      return
    }
    if (form.amount === '' || Number(form.amount) < 0) {
      setError('Enter a valid price.')
      return
    }
    if (form.durationValue !== '' && (!Number(form.durationValue) || Number(form.durationValue) <= 0)) {
      setError('Enter a valid plan duration.')
      return
    }

    setSaving(true)
    try {
      await onSave({
        display_name: form.displayName.trim(),
        description: form.description.trim() || null,
        amount: Number(form.amount).toFixed(2),
        currency: form.currency.toUpperCase(),
        duration_seconds: form.durationValue === ''
          ? null
          : Math.round(Number(form.durationValue) * DURATION_UNITS[form.durationUnit]),
        data_limit_bytes: form.dataLimitGb === ''
          ? null
          : Math.round(Number(form.dataLimitGb) * 1024 ** 3),
        device_limit: form.deviceLimit === '' ? null : Number(form.deviceLimit),
        download_speed: form.downloadSpeed.trim() || null,
        is_promotional: profile.is_registration_profile ? false : form.isPromotional,
        is_visible: profile.is_registration_profile ? false : form.isVisible,
      })
    } catch (saveError) {
      setError(saveError.message || 'The profile could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  async function removeConfiguration() {
    if (!confirmingDelete) {
      setConfirmingDelete(true)
      setError('')
      return
    }

    setDeleting(true)
    setError('')
    try {
      await onDelete()
    } catch (deleteError) {
      setError(deleteError.message || 'The profile configuration could not be deleted.')
      setConfirmingDelete(false)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="profile-drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        aria-labelledby="profile-editor-title"
        aria-modal="true"
        className="profile-drawer"
        role="dialog"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="profile-drawer-header">
          <div>
            <p className="dashboard-kicker">{hostel.name}</p>
            <h2 id="profile-editor-title">{profile.is_configured ? 'Edit plan' : 'Configure profile'}</h2>
          </div>
          <button aria-label="Close profile editor" type="button" onClick={onClose}><Icon name="close" /></button>
        </header>

        <div className="native-profile-card">
          <span><Icon name="tag" /></span>
          <div>
            <small>MikroTik profile</small>
            <strong>{profile.mikrotik_profile}</strong>
            <p>The router profile name stays unchanged.</p>
          </div>
        </div>

        {profile.bulk_mode && <div className={`bulk-profile-notice ${profile.configuration_consistent ? '' : 'mixed'}`}>
          <Icon name={profile.configuration_consistent ? 'check' : 'alert'} />
          <div><strong>Configure {profile.hostel_count} hostels together</strong><p>{profile.configuration_consistent ? 'Saving will apply these settings to every hostel where this profile exists.' : `${profile.configured_hostels} of ${profile.hostel_count} hostels are configured, with differing settings. Mixed fields are blank; saving will replace the settings on every hostel.`}</p></div>
        </div>}

        <form className="profile-editor-form" onSubmit={submit}>
          <section>
            <div className="editor-section-heading">
              <span>1</span><div><h3>Customer presentation</h3><p>How this plan appears in the purchase portal.</p></div>
            </div>
            <label className="editor-field">
              <span>Display name</span>
              <input maxLength="120" name="displayName" placeholder="e.g. Weekly Freedom" value={form.displayName} onChange={change} />
              <small>Customers will see this instead of “{profile.mikrotik_profile}”.</small>
            </label>
            <label className="editor-field">
              <span>Description <em>Optional</em></span>
              <textarea maxLength="500" name="description" placeholder="A short, helpful summary of this plan" rows="3" value={form.description} onChange={change} />
            </label>
          </section>

          <section>
            <div className="editor-section-heading">
              <span>2</span><div><h3>Price and validity</h3><p>Commercial terms shown before purchase.</p></div>
            </div>
            <div className="editor-two-columns">
              <label className="editor-field">
                <span>Price</span>
                <div className="input-prefix"><b>{form.currency}</b><input min="0" name="amount" placeholder="0.00" step="0.01" type="number" value={form.amount} onChange={change} /></div>
              </label>
              <label className="editor-field">
                <span>Currency</span>
                <select name="currency" value={form.currency} onChange={change}><option value="GHS">GHS - Ghana cedi</option></select>
              </label>
            </div>
            <div className="editor-two-columns duration-columns">
              <label className="editor-field">
                <span>Duration <em>Optional</em></span>
                <input min="1" name="durationValue" placeholder="No fixed duration" step="1" type="number" value={form.durationValue} onChange={change} />
                <small>Leave blank when this plan has no fixed validity period.</small>
              </label>
              <label className="editor-field unit-field">
                <span>Unit</span>
                <select disabled={form.durationValue === ''} name="durationUnit" value={form.durationUnit} onChange={change}>
                  <option value="hours">Hours</option><option value="days">Days</option><option value="weeks">Weeks</option><option value="months">Months</option>
                </select>
              </label>
            </div>
          </section>

          <section>
            <div className="editor-section-heading">
              <span>3</span><div><h3>Plan limits</h3><p>Useful details customers use to compare plans.</p></div>
            </div>
            <div className="editor-two-columns">
              <label className="editor-field">
                <span>Data allowance <em>GB, optional</em></span>
                <input min="0.01" name="dataLimitGb" placeholder="Unlimited" step="0.01" type="number" value={form.dataLimitGb} onChange={change} />
              </label>
              <label className="editor-field">
                <span>Device limit <em>Optional</em></span>
                <input max="100" min="1" name="deviceLimit" placeholder="Unlimited" step="1" type="number" value={form.deviceLimit} onChange={change} />
              </label>
            </div>
            <label className="editor-field">
              <span>Download speed <em>Optional</em></span>
              <input maxLength="40" name="downloadSpeed" placeholder="e.g. 10 Mbps" value={form.downloadSpeed} onChange={change} />
              <small>Prefilled from the router rate limit when available. Customers only see this download speed.</small>
            </label>
          </section>

          <section className="visibility-section">
            <label className={profile.is_registration_profile ? 'publish-toggle disabled' : 'publish-toggle'}>
              <div><strong>Promotional package</strong><small>{profile.is_registration_profile ? 'The registration profile cannot be used as a promotion.' : 'Highlight this offer publicly and allow each customer to purchase it only once.'}</small></div>
              <input checked={profile.is_registration_profile ? false : form.isPromotional} disabled={profile.is_registration_profile} name="isPromotional" type="checkbox" onChange={change} />
              <span aria-hidden="true" />
            </label>
            <label className={profile.is_registration_profile ? 'publish-toggle disabled' : 'publish-toggle'}>
              <div><strong>Publish to customers</strong><small>{profile.is_registration_profile ? 'This system profile is reserved for registration.' : 'Make this plan available on the customer purchase page.'}</small></div>
              <input checked={form.isVisible} disabled={profile.is_registration_profile} name="isVisible" type="checkbox" onChange={change} />
              <span aria-hidden="true" />
            </label>
          </section>

          {error && <div className="editor-error" role="alert"><Icon name="alert" />{error}</div>}

          {canDelete && <div className="configuration-delete-panel">
            <div><strong>Delete saved configuration</strong><small>This removes the customer plan settings only. The profile on the MikroTik router will not be deleted.</small></div>
            <button className={confirmingDelete ? 'confirming' : ''} disabled={saving || deleting} type="button" onClick={removeConfiguration}>{deleting ? 'Deleting...' : confirmingDelete ? 'Confirm delete' : 'Delete configuration'}</button>
          </div>}

          <footer className="profile-drawer-actions">
            <button className="drawer-cancel" disabled={saving || deleting} type="button" onClick={onClose}>Cancel</button>
            <button className="drawer-save" disabled={saving || deleting} type="submit">{saving ? 'Saving changes...' : 'Save changes'}</button>
          </footer>
        </form>
      </aside>
    </div>
  )
}

function HostelEditor({ hostel, canEdit, onClose, onSave }) {
  const isNew = !hostel
  const [form, setForm] = useState({
    routerId: hostel?.router_id || '',
    name: hostel?.name || '',
    location: hostel?.location || '',
    vpnHost: hostel?.vpn_host || '',
    apiPort: hostel?.api_port || 8728,
    hotspotNetwork: hostel?.hotspot_network || '',
    displayOrder: hostel?.display_order ?? 0,
    isActive: hostel?.is_active ?? true,
  })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  function change(event) {
    const { name, value, checked, type } = event.target
    setForm((current) => ({ ...current, [name]: type === 'checkbox' ? checked : value }))
    setError('')
  }

  async function submit(event) {
    event.preventDefault()
    if (!canEdit) return
    if ((isNew && !/^[a-z0-9][a-z0-9-]{1,63}$/.test(form.routerId)) || form.name.trim().length < 2 || !form.vpnHost.trim() || (isNew && !form.hotspotNetwork.trim())) {
      setError(isNew ? 'Enter a valid hostel ID, name, VPN host, and hotspot network.' : 'Enter a hostel name and VPN host.')
      return
    }
    setSaving(true)
    try {
      await onSave({
        ...(isNew ? { router_id: form.routerId } : {}),
        name: form.name.trim(),
        location: form.location.trim() || null,
        vpn_host: form.vpnHost.trim(),
        api_port: Number(form.apiPort),
        hotspot_network: form.hotspotNetwork.trim() || null,
        display_order: Number(form.displayOrder),
        is_active: form.isActive,
      })
    } catch (saveError) {
      setError(saveError.message || 'The hostel details could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="profile-drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside aria-labelledby="hostel-editor-title" aria-modal="true" className="profile-drawer hostel-drawer" role="dialog" onMouseDown={(event) => event.stopPropagation()}>
        <header className="profile-drawer-header">
          <div><p className="dashboard-kicker">Database record</p><h2 id="hostel-editor-title">{isNew ? 'Add hostel' : 'Hostel details'}</h2></div>
          <button aria-label="Close hostel details" type="button" onClick={onClose}><Icon name="close" /></button>
        </header>

        {!isNew && <div className="hostel-record-summary">
          <span><Icon name="building" /></span>
          <div><small>Stable hostel ID</small><strong>{hostel.router_id}</strong><p>This identifier cannot be changed because customer and payment records refer to it.</p></div>
        </div>}

        <form className="profile-editor-form hostel-editor-form" onSubmit={submit}>
          <section>
            <div className="editor-section-heading"><span>1</span><div><h3>Public details</h3><p>The name and location shown across the service.</p></div></div>
            {isNew && <label className="editor-field"><span>Hostel ID</span><input autoCapitalize="none" maxLength="64" name="routerId" placeholder="e.g. platinum-hostel" spellCheck="false" value={form.routerId} onChange={(event) => setForm((current) => ({ ...current, routerId: event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '') }))} /><small>Use lowercase letters, numbers, and hyphens. This cannot be changed later.</small></label>}
            <label className="editor-field"><span>Hostel name</span><input disabled={!canEdit} maxLength="120" name="name" value={form.name} onChange={change} /></label>
            <label className="editor-field"><span>Location <em>Optional</em></span><input disabled={!canEdit} maxLength="255" name="location" placeholder="e.g. North campus" value={form.location} onChange={change} /></label>
          </section>

          <section>
            <div className="editor-section-heading"><span>2</span><div><h3>Router connection</h3><p>Database settings used to reach this hostel&apos;s MikroTik router.</p></div></div>
            <label className="editor-field"><span>VPN host</span><input disabled={!canEdit} maxLength="255" name="vpnHost" value={form.vpnHost} onChange={change} /></label>
            <div className="editor-two-columns">
              <label className="editor-field"><span>API port</span><input disabled={!canEdit} max="65535" min="1" name="apiPort" step="1" type="number" value={form.apiPort} onChange={change} /></label>
              <label className="editor-field"><span>Display order</span><input disabled={!canEdit} min="0" name="displayOrder" step="1" type="number" value={form.displayOrder} onChange={change} /></label>
            </div>
            <label className="editor-field"><span>Hotspot network <em>Optional</em></span><input disabled={!canEdit} maxLength="255" name="hotspotNetwork" placeholder="e.g. 192.168.88.0/24" value={form.hotspotNetwork} onChange={change} /></label>
          </section>

          <section className="visibility-section">
            <label className={canEdit ? 'publish-toggle' : 'publish-toggle disabled'}>
              <div><strong>Hostel active</strong><small>Allow customers to select and use this hostel.</small></div>
              <input checked={form.isActive} disabled={!canEdit} name="isActive" type="checkbox" onChange={change} /><span aria-hidden="true" />
            </label>
          </section>

          {!canEdit && !isNew && <div className="hostel-readonly-note"><Icon name="alert" />Your viewer role has read-only access to these details.</div>}
          {error && <div className="editor-error" role="alert"><Icon name="alert" />{error}</div>}
          <footer className="profile-drawer-actions">
            <button className="drawer-cancel" disabled={saving} type="button" onClick={onClose}>{canEdit ? 'Cancel' : 'Close'}</button>
            {canEdit && <button className="drawer-save" disabled={saving} type="submit">{saving ? 'Saving details...' : isNew ? 'Add hostel' : 'Save details'}</button>}
          </footer>
        </form>
      </aside>
    </div>
  )
}

function HostelTable({ actionError, forcingRouterId, hostels, canEdit, loading, onAdd, onEdit, onForceUpdate, onProfiles }) {
  return (
    <section className="hostels-card">
      <header className="hostels-card-heading">
        <div><h2>All hostels</h2><p>View and manage the router locations stored in the database.</p></div>
        {canEdit && <button type="button" onClick={onAdd}>+ Add hostel</button>}
      </header>
      {actionError && <div className="hostel-action-error" role="alert"><Icon name="alert" />{actionError}</div>}
      {loading ? (
        <div className="profiles-loading"><span className="admin-page-spinner" /><p>Loading hostel records...</p></div>
      ) : !hostels.length ? (
        <div className="profiles-empty"><Icon name="building" /><h3>No hostels added</h3><p>Add your first hostel to begin configuring WiFi plans.</p></div>
      ) : (
        <div className="hostels-table-wrap">
          <table className="hostels-table">
            <thead><tr><th>Hostel</th><th>Connection</th><th>Plans</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>{hostels.map((hostel) => <tr key={hostel.router_id}>
              <td><div className="hostel-name-cell"><span><Icon name="building" /></span><div><strong>{hostel.name}</strong><small>{hostel.location || hostel.router_id}</small></div></div></td>
              <td><div className="router-details"><span>{hostel.vpn_host}:{hostel.api_port}</span><small>{hostel.hotspot_network || 'Network not set'}</small></div></td>
              <td><div className="router-details"><span>{hostel.published_profiles} published</span><small>{hostel.configured_profiles} configured</small></div></td>
              <td><span className={`hostel-state ${hostel.is_active ? 'active' : ''}`}><i />{hostel.is_active ? 'Active' : 'Inactive'}</span></td>
              <td><div className="hostel-row-actions">{canEdit && <button disabled={Boolean(forcingRouterId)} title="Run IP Cloud Force Update on this router" type="button" onClick={() => onForceUpdate(hostel)}>{forcingRouterId === hostel.router_id ? 'Updating...' : 'Force IP update'}</button>}<button disabled={Boolean(forcingRouterId)} type="button" onClick={() => onEdit(hostel.router_id)}>{canEdit ? 'Edit' : 'View'}</button><button disabled={Boolean(forcingRouterId)} type="button" onClick={() => onProfiles(hostel.router_id)}>Plans</button></div></td>
            </tr>)}</tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function SupportSettingsPanel({ canEdit, onSessionExpired }) {
  const [form, setForm] = useState({ phoneNumber: '', whatsappUrl: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    let active = true
    getSupportSettings()
      .then((settings) => {
        if (!active) return
        setForm({
          phoneNumber: settings.phone_number || '',
          whatsappUrl: settings.whatsapp_url || '',
        })
      })
      .catch((requestError) => {
        if (!active) return
        if (requestError instanceof AdminApiError && requestError.status === 401) {
          onSessionExpired()
          return
        }
        setError('Support details could not be loaded.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [onSessionExpired])

  function change(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
    setError('')
    setSuccess('')
  }

  async function submit(event) {
    event.preventDefault()
    const phoneDigits = form.phoneNumber.replace(/\D/g, '')
    if (form.phoneNumber && (phoneDigits.length < 7 || phoneDigits.length > 15)) {
      setError('Enter a valid support phone number.')
      return
    }
    if (form.whatsappUrl && !/^(https:\/\/)?(wa\.me|api\.whatsapp\.com|web\.whatsapp\.com)\//i.test(form.whatsappUrl)) {
      setError('Use an official WhatsApp link, such as https://wa.me/233XXXXXXXXX.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const saved = await saveSupportSettings({
        phone_number: form.phoneNumber.trim() || null,
        whatsapp_url: form.whatsappUrl.trim() || null,
      })
      setForm({
        phoneNumber: saved.phone_number || '',
        whatsappUrl: saved.whatsapp_url || '',
      })
      setSuccess('Help and support details saved and published to the public pages.')
    } catch (requestError) {
      if (requestError instanceof AdminApiError && requestError.status === 401) {
        onSessionExpired()
        return
      }
      setError('Support details could not be saved. Check the values and try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <header className="dashboard-page-heading"><div><p className="dashboard-kicker">Public contact</p><h1>Help &amp; support</h1><p>Manage the contact options displayed throughout the customer service.</p></div></header>
      <section className="support-settings-card">
        <header><span><Icon name="settings" /></span><div><h2>Support contacts</h2><p>Changes appear automatically on every public page.</p></div></header>
        {loading ? <div className="profiles-loading"><span className="admin-page-spinner" /><p>Loading support details...</p></div> : <form onSubmit={submit}>
          <label><span>Help and support phone number</span><input disabled={!canEdit} maxLength="40" name="phoneNumber" placeholder="e.g. +233 20 000 0000" type="tel" value={form.phoneNumber} onChange={change} /><small>Customers can tap this number to call from supported devices.</small></label>
          <label><span>WhatsApp support link</span><input disabled={!canEdit} maxLength="500" name="whatsappUrl" placeholder="https://wa.me/233200000000" type="url" value={form.whatsappUrl} onChange={change} /><small>Use an official wa.me or whatsapp.com HTTPS link.</small></label>
          <div className="support-settings-preview"><strong>Public preview</strong><div>{form.phoneNumber ? <span>☎ {form.phoneNumber}</span> : <em>No phone number</em>}{form.whatsappUrl ? <span className="whatsapp">◉ WhatsApp</span> : <em>No WhatsApp link</em>}</div></div>
          {!canEdit && <div className="hostel-readonly-note"><Icon name="alert" />Your viewer role has read-only access to these settings.</div>}
          {error && <div className="editor-error" role="alert"><Icon name="alert" />{error}</div>}
          {success && <div className="support-settings-success" role="status"><Icon name="check" />{success}</div>}
          {canEdit && <button className="support-settings-save" disabled={saving} type="submit">{saving ? 'Saving...' : 'Save and publish'}</button>}
        </form>}
      </section>
    </>
  )
}

function ProfileTable({ bulkMode, profiles, query, filter, onEdit }) {
  const visibleProfiles = profiles.filter((profile) => {
    const matchesQuery = `${profile.display_name || ''} ${profile.mikrotik_profile}`
      .toLowerCase().includes(query.toLowerCase())
    const matchesFilter = filter === 'all'
      || (filter === 'published' && profile.is_visible)
      || (filter === 'drafts' && !profile.is_visible)
    return matchesQuery && matchesFilter
  })

  if (!visibleProfiles.length) {
    return <div className="profiles-empty"><Icon name="search" /><h3>{bulkMode && !query && filter === 'all' ? 'No shared profiles' : 'No matching profiles'}</h3><p>{bulkMode && !query && filter === 'all' ? 'Only profiles available on every hostel are shown here.' : 'Try another search or filter.'}</p></div>
  }

  return (
    <div className="profiles-table-wrap">
      <table className="profiles-table">
        <thead><tr><th>Customer plan</th><th>Router settings</th><th>Price and validity</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>
          {visibleProfiles.map((profile) => {
            const status = statusFor(profile)
            return (
              <tr key={profile.mikrotik_profile}>
                <td>
                  <div className="profile-name-cell">
                    <span className={profile.is_visible ? 'profile-table-icon active' : 'profile-table-icon'}><Icon name="tag" /></span>
                    <div>
                      <span className="profile-title-line">
                        <strong>{profile.display_name || titleFromProfile(profile.mikrotik_profile)}</strong>
                        {profile.is_promotional && <em>Promo</em>}
                      </span>
                      <small>{profile.mikrotik_profile}</small>
                    </div>
                  </div>
                </td>
                <td><div className="router-details"><span>{profile.rate_limit || 'No rate limit'}</span><small>{profile.download_speed ? `${profile.download_speed} download` : 'Download speed not set'}</small></div></td>
                <td><div className="router-details"><span>{formatMoney(profile.amount, profile.currency)}</span><small>{formatDuration(profile.duration_seconds)}</small></div></td>
                <td><span className={`profile-status ${status.className}`}><i />{status.label}</span></td>
                <td><button className="profile-edit-button" disabled={!profile.available_on_router} type="button" onClick={() => onEdit(profile)}>{profile.bulk_mode ? (profile.is_configured ? 'Edit all' : 'Configure all') : (profile.is_configured ? 'Edit' : 'Configure')}<Icon name="chevron" /></button></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function AdminDashboard({ admin, onSessionExpired }) {
  const [view, setView] = useState('profiles')
  const [hostels, setHostels] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [profiles, setProfiles] = useState([])
  const [loadingHostels, setLoadingHostels] = useState(true)
  const [loadingProfiles, setLoadingProfiles] = useState(false)
  const [pageError, setPageError] = useState('')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [editingProfile, setEditingProfile] = useState(null)
  const [viewingHostel, setViewingHostel] = useState(false)
  const [toast, setToast] = useState('')
  const [hostelActionError, setHostelActionError] = useState('')
  const [forcingRouterId, setForcingRouterId] = useState('')
  const [signingOut, setSigningOut] = useState(false)

  const bulkHostels = hostels.filter((hostel) => hostel.is_active)
  const allHostelsSelected = selectedId === ALL_HOSTELS_ID
  const selectedHostel = allHostelsSelected
    ? {
      router_id: ALL_HOSTELS_ID,
      name: 'All hostels',
      location: `${bulkHostels.length} active router${bulkHostels.length === 1 ? '' : 's'} selected`,
      is_active: bulkHostels.length > 0,
      status: bulkHostels.length > 0 && bulkHostels.every((hostel) => hostel.status === 'online') ? 'online' : 'unknown',
    }
    : hostels.find((hostel) => hostel.router_id === selectedId) || null
  const totals = useMemo(() => ({
    hostels: hostels.length,
    online: hostels.filter((hostel) => hostel.status === 'online').length,
    published: hostels.reduce((sum, hostel) => sum + hostel.published_profiles, 0),
  }), [hostels])

  function handleError(error, fallback) {
    if (error instanceof AdminApiError && error.status === 401) {
      onSessionExpired()
      return
    }
    setPageError(fallback)
  }

  async function listProfilesForSelection(routerId) {
    if (routerId !== ALL_HOSTELS_ID) return listHostelProfiles(routerId)

    const results = await Promise.allSettled(
      bulkHostels.map((hostel) => listHostelProfiles(hostel.router_id)),
    )
    const failedRouterIds = new Set(results.flatMap((result, index) => (
      result.status === 'rejected' ? [bulkHostels[index].router_id] : []
    )))
    setHostels((current) => current.map((hostel) => ({
      ...hostel,
      status: failedRouterIds.has(hostel.router_id) ? 'offline' : 'online',
      ...(!failedRouterIds.has(hostel.router_id) ? { last_seen_at: new Date().toISOString() } : {}),
    })))

    const failedResult = results.find((result) => result.status === 'rejected')
    if (failedResult) throw failedResult.reason
    return profilesCommonToAll(results.map((result) => result.value))
  }

  useEffect(() => {
    let active = true
    listHostels()
      .then((items) => {
        if (!active) return
        setHostels(items)
        setSelectedId((current) => current || items.find((item) => item.is_active)?.router_id || items[0]?.router_id || '')
      })
      .catch((error) => handleError(error, 'The hostel catalogue could not be loaded.'))
      .finally(() => { if (active) setLoadingHostels(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!selectedId || view !== 'profiles') return
    let active = true
    setLoadingProfiles(true)
    setPageError('')
    listProfilesForSelection(selectedId)
      .then((items) => {
        if (!active) return
        setProfiles(items)
        if (selectedId !== ALL_HOSTELS_ID) {
          setHostels((current) => current.map((hostel) => (
            hostel.router_id === selectedId
              ? { ...hostel, status: 'online', last_seen_at: new Date().toISOString() }
              : hostel
          )))
        }
      })
      .catch((error) => {
        if (!active) return
        if (selectedId !== ALL_HOSTELS_ID) {
          setHostels((current) => current.map((hostel) => (
            hostel.router_id === selectedId ? { ...hostel, status: 'offline' } : hostel
          )))
        }
        handleError(error, selectedId === ALL_HOSTELS_ID
          ? 'Every hostel must be reachable to list their shared profiles. Check the offline router and try again.'
          : 'The router could not be reached. Check its connection and try again.')
      })
      .finally(() => { if (active) setLoadingProfiles(false) })
    return () => { active = false }
  }, [selectedId, view])

  async function refreshProfiles() {
    if (!selectedId) return
    setLoadingProfiles(true)
    setPageError('')
    try {
      setProfiles(await listProfilesForSelection(selectedId))
      setToast(allHostelsSelected ? 'Shared profiles refreshed from all routers.' : 'Profiles refreshed from the router.')
      window.setTimeout(() => setToast(''), 3000)
    } catch (error) {
      if (!allHostelsSelected) {
        setHostels((current) => current.map((hostel) => (
          hostel.router_id === selectedId ? { ...hostel, status: 'offline' } : hostel
        )))
      }
      handleError(error, allHostelsSelected
        ? 'Every hostel must be reachable to list their shared profiles. Check the offline router and try again.'
        : 'The router could not be reached. Check its connection and try again.')
    } finally {
      setLoadingProfiles(false)
    }
  }

  async function saveProfile(payload) {
    if (allHostelsSelected) {
      const results = await Promise.allSettled(bulkHostels.map((hostel) => (
        saveHostelProfile(hostel.router_id, editingProfile.mikrotik_profile, payload)
      )))
      const sessionFailure = results.find((result) => (
        result.status === 'rejected'
        && result.reason instanceof AdminApiError
        && result.reason.status === 401
      ))
      if (sessionFailure) onSessionExpired()

      const savedCount = results.filter((result) => result.status === 'fulfilled').length
      if (savedCount !== bulkHostels.length) {
        try { setHostels(await listHostels()) } catch { /* Keep the current catalogue. */ }
        throw new Error(`Saved ${savedCount} of ${bulkHostels.length} hostels. Retry to update the remaining hostels.`)
      }

      const saved = profilesCommonToAll(results.map((result) => [result.value]))[0]
      setProfiles((current) => current.map((profile) => (
        profile.mikrotik_profile.toLocaleLowerCase() === saved.mikrotik_profile.toLocaleLowerCase()
          ? saved
          : profile
      )))
      setEditingProfile(null)
      setToast(`Plan saved for all ${bulkHostels.length} active hostels.`)
      window.setTimeout(() => setToast(''), 3500)
      try { setHostels(await listHostels()) } catch (error) {
        if (error instanceof AdminApiError && error.status === 401) onSessionExpired()
      }
      return
    }

    let saved
    try {
      saved = await saveHostelProfile(selectedId, editingProfile.mikrotik_profile, payload)
    } catch (error) {
      if (error instanceof AdminApiError && error.status === 401) onSessionExpired()
      throw new Error(
        error instanceof AdminApiError && error.status === 400
          ? 'This system profile cannot be published.'
          : 'The profile could not be saved. Please try again.',
      )
    }
    setProfiles((current) => current.map((profile) => (
      profile.mikrotik_profile === saved.mikrotik_profile ? saved : profile
    )))
    setEditingProfile(null)
    setToast(saved.is_visible ? 'Plan saved and published to customers.' : 'Plan saved as a draft.')
    window.setTimeout(() => setToast(''), 3500)
    try {
      setHostels(await listHostels())
    } catch (error) {
      if (error instanceof AdminApiError && error.status === 401) onSessionExpired()
    }
  }

  async function deleteProfileConfiguration() {
    const targetHostels = allHostelsSelected ? bulkHostels : [selectedHostel]
    const results = await Promise.allSettled(targetHostels.map((hostel) => (
      deleteHostelProfileConfiguration(hostel.router_id, editingProfile.mikrotik_profile)
    )))
    const sessionFailure = results.find((result) => (
      result.status === 'rejected'
      && result.reason instanceof AdminApiError
      && result.reason.status === 401
    ))
    if (sessionFailure) onSessionExpired()

    const deletedCount = results.filter((result) => result.status === 'fulfilled').length
    if (deletedCount !== targetHostels.length) {
      try { setHostels(await listHostels()) } catch { /* Keep the current catalogue. */ }
      throw new Error(allHostelsSelected
        ? `Deleted ${deletedCount} of ${targetHostels.length} configurations. Retry to remove the remaining configurations.`
        : 'The profile configuration could not be deleted. Please try again.')
    }

    setProfiles((current) => current.map((profile) => (
      profile.mikrotik_profile.toLocaleLowerCase()
        === editingProfile.mikrotik_profile.toLocaleLowerCase()
        ? withoutProfileConfiguration(profile)
        : profile
    )))
    setEditingProfile(null)
    setToast(allHostelsSelected
      ? `Configuration deleted from all ${targetHostels.length} active hostels. Router profiles were not changed.`
      : 'Configuration deleted. The MikroTik profile was not changed.')
    window.setTimeout(() => setToast(''), 4000)
    try { setHostels(await listHostels()) } catch (error) {
      if (error instanceof AdminApiError && error.status === 401) onSessionExpired()
    }
  }

  async function signOut() {
    setSigningOut(true)
    try { await logout() } finally { onSessionExpired() }
  }

  async function saveHostel(payload) {
    try {
      const saved = await updateHostel(selectedId, payload)
      setHostels((current) => current
        .map((hostel) => hostel.router_id === saved.router_id ? saved : hostel)
        .sort((left, right) => left.display_order - right.display_order || left.name.localeCompare(right.name)))
      setViewingHostel(false)
      setToast('Hostel details saved.')
      window.setTimeout(() => setToast(''), 3500)
    } catch (error) {
      if (error instanceof AdminApiError && error.status === 401) onSessionExpired()
      throw new Error(error instanceof AdminApiError && error.status === 409
        ? 'That VPN host is already assigned to another hostel.'
        : 'The hostel details could not be saved. Please try again.')
    }
  }

  async function addHostel(payload) {
    try {
      const saved = await createHostel(payload)
      setHostels((current) => [...current, saved]
        .sort((left, right) => left.display_order - right.display_order || left.name.localeCompare(right.name)))
      setSelectedId(saved.router_id)
      setViewingHostel(false)
      setToast('Hostel added successfully.')
      window.setTimeout(() => setToast(''), 3500)
    } catch (error) {
      if (error instanceof AdminApiError && error.status === 401) onSessionExpired()
      throw new Error(error instanceof AdminApiError && error.status === 409
        ? 'That hostel ID or VPN host is already in use.'
        : 'The hostel could not be added. Please try again.')
    }
  }

  async function forceIpCloudUpdate(hostel) {
    setForcingRouterId(hostel.router_id)
    setHostelActionError('')
    try {
      const updated = await forceHostelIpCloudUpdate(hostel.router_id)
      setHostels((current) => current.map((item) => (
        item.router_id === updated.router_id ? updated : item
      )))
      setToast(`IP Cloud force update sent to ${hostel.name}.`)
      window.setTimeout(() => setToast(''), 3500)
    } catch (error) {
      if (error instanceof AdminApiError && error.status === 401) {
        onSessionExpired()
        return
      }
      if (error instanceof AdminApiError && [502, 503, 504].includes(error.status)) {
        setHostels((current) => current.map((item) => (
          item.router_id === hostel.router_id ? { ...item, status: 'offline' } : item
        )))
      }
      setHostelActionError(`Could not force the IP Cloud update for ${hostel.name}. Check the router connection and try again.`)
    } finally {
      setForcingRouterId('')
    }
  }

  function openHostel(routerId) {
    setSelectedId(routerId)
    setViewingHostel('details')
  }

  function openProfiles(routerId) {
    setSelectedId(routerId)
    setView('profiles')
  }

  return (
    <div className="admin-dashboard">
      <aside className="dashboard-sidebar">
        <Brand />
        <nav aria-label="Admin navigation">
          <p>Workspace</p>
          <button className={view === 'hostels' ? 'active' : ''} type="button" onClick={() => setView('hostels')}><Icon name="building" />Hostels</button>
          <button className={view === 'profiles' ? 'active' : ''} type="button" onClick={() => setView('profiles')}><Icon name="tag" />Profile catalogue</button>
          <p>Management</p>
          <button className="coming-soon" disabled type="button"><Icon name="users" />Customers<small>Soon</small></button>
          <button className="coming-soon" disabled type="button"><Icon name="receipt" />Transactions<small>Soon</small></button>
          <button className={view === 'support' ? 'active' : ''} type="button" onClick={() => setView('support')}><Icon name="settings" />Help &amp; support</button>
        </nav>
        <div className="sidebar-security"><span><Icon name="check" /></span><div><strong>Secure session</strong><small>Protected admin access</small></div></div>
      </aside>

      <main className="dashboard-main">
        <header className="dashboard-topbar">
          <div className="mobile-dashboard-brand"><Brand /></div>
          <div className="dashboard-admin-menu">
            <span className="admin-avatar">{admin.username.slice(0, 1).toUpperCase()}</span>
            <div><strong>{admin.username}</strong><small>{admin.role}</small></div>
            <button aria-label="Sign out" disabled={signingOut} type="button" onClick={signOut}><Icon name="logout" /></button>
          </div>
        </header>

        <div className="dashboard-content">
          <div className="dashboard-mobile-tabs"><button className={view === 'hostels' ? 'active' : ''} type="button" onClick={() => setView('hostels')}>Hostels</button><button className={view === 'profiles' ? 'active' : ''} type="button" onClick={() => setView('profiles')}>Profiles</button><button className={view === 'support' ? 'active' : ''} type="button" onClick={() => setView('support')}>Support</button></div>
          {view === 'support' ? <SupportSettingsPanel canEdit={admin.role !== 'viewer'} onSessionExpired={onSessionExpired} /> : view === 'hostels' ? <>
            <header className="dashboard-page-heading">
              <div><p className="dashboard-kicker">Network management</p><h1>Hostels</h1><p>Add and manage the hostel routers stored in the database.</p></div>
            </header>
            <HostelTable actionError={hostelActionError} canEdit={admin.role !== 'viewer'} forcingRouterId={forcingRouterId} hostels={hostels} loading={loadingHostels} onAdd={() => setViewingHostel('new')} onEdit={openHostel} onForceUpdate={forceIpCloudUpdate} onProfiles={openProfiles} />
          </> : <>
          <header className="dashboard-page-heading">
            <div><p className="dashboard-kicker">Network catalogue</p><h1>Hostel profiles</h1><p>Turn MikroTik profiles into clear, customer-ready WiFi plans.</p></div>
            <div className="hostel-selector">
              <label htmlFor="hostel-select">Selected hostel</label>
              <div><Icon name="building" /><select disabled={loadingHostels || !hostels.length} id="hostel-select" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}><option disabled={!bulkHostels.length} value={ALL_HOSTELS_ID}>All hostels ({bulkHostels.length} active)</option>{hostels.map((hostel) => <option key={hostel.router_id} value={hostel.router_id}>{hostel.name}</option>)}</select></div>
            </div>
          </header>

          <section className="dashboard-stats" aria-label="Catalogue overview">
            <article><span className="stat-icon purple"><Icon name="building" /></span><div><small>Hostels</small><strong>{totals.hostels}</strong><p>Configured locations</p></div></article>
            <article><span className="stat-icon green"><Icon name="wifi" /></span><div><small>Online now</small><strong>{totals.online}</strong><p>Last verified connections</p></div></article>
            <article><span className="stat-icon blue"><Icon name="tag" /></span><div><small>Published plans</small><strong>{totals.published}</strong><p>Visible to customers</p></div></article>
          </section>

          <section className="profile-catalogue-card">
            <header className="catalogue-heading">
              <div>
                <span className={`hostel-live-dot ${selectedHostel?.status === 'online' ? 'online' : ''}`} />
                <div><h2>{selectedHostel?.name || 'Select a hostel'}</h2><p>{selectedHostel?.location || selectedHostel?.router_id || 'Choose a hostel to view its router profiles.'}</p></div>
              </div>
              <div className="catalogue-heading-actions">
                <button disabled={!selectedHostel || allHostelsSelected} type="button" onClick={() => setViewingHostel('details')}><Icon name="settings" />View details</button>
                <button disabled={loadingProfiles || !selectedHostel?.is_active} type="button" onClick={refreshProfiles}><Icon name="refresh" />{loadingProfiles ? 'Syncing...' : allHostelsSelected ? 'Sync all routers' : 'Sync from router'}</button>
              </div>
            </header>

            <div className="catalogue-toolbar">
              <div className="profile-search"><Icon name="search" /><input aria-label="Search profiles" placeholder="Search by plan or profile name" type="search" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
              <div className="profile-filters" aria-label="Filter profiles">{['all', 'published', 'drafts'].map((item) => <button className={filter === item ? 'active' : ''} key={item} type="button" onClick={() => setFilter(item)}>{item[0].toUpperCase() + item.slice(1)}</button>)}</div>
            </div>

            {pageError ? (
              <div className="profiles-error"><span><Icon name="alert" /></span><h3>Unable to load profiles</h3><p>{pageError}</p><button type="button" onClick={refreshProfiles}>Try again</button></div>
            ) : loadingProfiles ? (
              <div className="profiles-loading"><span className="admin-page-spinner" /><p>Reading profiles from {selectedHostel?.name || 'the router'}...</p></div>
            ) : !selectedId ? (
              <div className="profiles-empty"><Icon name="building" /><h3>No hostels configured</h3><p>Add a router to the backend catalogue to get started.</p></div>
            ) : (
              <ProfileTable bulkMode={allHostelsSelected} filter={filter} profiles={profiles} query={query} onEdit={setEditingProfile} />
            )}
          </section>
          </>}
        </div>
      </main>

      {editingProfile && selectedHostel && <ProfileEditor hostel={selectedHostel} profile={editingProfile} onClose={() => setEditingProfile(null)} onDelete={deleteProfileConfiguration} onSave={saveProfile} />}
      {viewingHostel === 'details' && selectedHostel && <HostelEditor canEdit={admin.role !== 'viewer'} hostel={selectedHostel} onClose={() => setViewingHostel(false)} onSave={saveHostel} />}
      {viewingHostel === 'new' && <HostelEditor canEdit hostel={null} onClose={() => setViewingHostel(false)} onSave={addHostel} />}
      {toast && <div className="dashboard-toast" role="status"><Icon name="check" />{toast}</div>}
    </div>
  )
}
