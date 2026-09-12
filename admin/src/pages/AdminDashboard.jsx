import { useEffect, useMemo, useState } from 'react'

import {
  AdminApiError,
  createAllHostelPlanGroup,
  createHostel,
  createPlanGroup,
  deleteAllHostelPlanGroup,
  deleteCustomer,
  deleteHostelProfileConfiguration,
  deletePlanGroup,
  forceHostelIpCloudUpdate,
  getAccessPoints,
  getAdminSession,
  getCustomersAndDevices,
  getDashboard,
  getSupportSettings,
  getTransactions,
  listAllHostelPlanGroups,
  listHostelProfiles,
  listHostels,
  listPlanGroups,
  logout,
  saveHostelProfile,
  saveSupportSettings,
  sendBroadcast,
  transferCustomerHostel,
  updateAllHostelPlanGroup,
  updateHostel,
  updatePlanGroup,
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
    menu: <><path d="M4 6h16M4 12h16M4 18h16" /></>,
    back: <><path d="m14 6-6 6 6 6" /><path d="M8 12h12" /></>,
    wifi: <><path d="M4.9 9.5a10.4 10.4 0 0 1 14.2 0M7.6 12.7a6.4 6.4 0 0 1 8.8 0M10.4 16a2.4 2.4 0 0 1 3.2 0" /><circle cx="12" cy="19" r="1" /></>,
    check: <path d="m5 12 4.2 4.2L19 6.5" />,
    alert: <><path d="M10.3 3.8 2.5 17.2A2 2 0 0 0 4.2 20h15.6a2 2 0 0 0 1.7-2.8L13.7 3.8a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></>,
    logout: <><path d="M10 17l5-5-5-5M15 12H3M15 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4" /></>,
    device: <><rect x="5" y="2" width="14" height="20" rx="2" /><path d="M9 18h6" /></>,
    money: <><circle cx="12" cy="12" r="9" /><path d="M15 8.5c-.7-.7-1.7-1-3-1-1.7 0-3 .8-3 2s1.1 1.8 3 2.3 3 1 3 2.3-1.3 2.2-3 2.2c-1.2 0-2.4-.4-3.2-1.2M12 5.5v13" /></>,
    activity: <path d="M3 12h4l2.2-6 4.1 12 2.2-6H21" />,
    network: <><rect x="9" y="2.5" width="6" height="5" rx="1" /><rect x="2.5" y="16.5" width="6" height="5" rx="1" /><rect x="15.5" y="16.5" width="6" height="5" rx="1" /><path d="M12 7.5v4M5.5 16.5v-2h13v2" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  }
  return <svg aria-hidden="true" viewBox="0 0 24 24">{paths[name]}</svg>
}

function Brand() {
  return (
    <div className="dashboard-brand">
      <span><Icon name="wifi" /></span>
      <div><strong>Vlad WiFi</strong><small>Admin console</small></div>
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

function ProfileEditor({ groups, hostel, profile, onClose, onDelete, onSave }) {
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
    groupId: profile.group_id || '',
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
    if (Number(form.amount) === 0 && form.isVisible && !form.isPromotional) {
      setError('A published free plan must be marked as a promotional package.')
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
        ...(!profile.bulk_mode ? { group_id: form.groupId || null } : {}),
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
            {!profile.bulk_mode && <label className="editor-field">
              <span>Plan group <em>Optional</em></span>
              <select name="groupId" value={form.groupId} onChange={change}>
                <option value="">Ungrouped</option>
                {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
              </select>
              <small>Create and organize groups from the catalogue page.</small>
            </label>}
          </section>

          <section>
            <div className="editor-section-heading">
              <span>2</span><div><h3>Price and validity</h3><p>Commercial terms shown before purchase.</p></div>
            </div>
            <div className="editor-two-columns">
              <label className="editor-field">
                <span>Price</span>
                <div className="input-prefix"><b>{form.currency}</b><input min="0" name="amount" placeholder="0.00" step="0.01" type="number" value={form.amount} onChange={change} /></div>
                <small>Set this to 0 and enable Promotional package to offer a free one-time claim.</small>
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
              <div><strong>Promotional package</strong><small>{profile.is_registration_profile ? 'The registration profile cannot be used as a promotion.' : 'Show this offer first and allow each customer to use it once. A price of 0 makes it free.'}</small></div>
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

function PlanGroupManager({ bulkMode = false, canEdit, groups, onCreate, onDelete, onUpdate, profiles }) {
  const empty = { name: '', description: '', displayOrder: 0, sortByPrice: false, profileNames: [] }
  const [editingId, setEditingId] = useState('')
  const [form, setForm] = useState(empty)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [planSearch, setPlanSearch] = useState('')
  const publishedPlans = profiles
    .filter((profile) => profile.is_visible && profile.is_configured && !profile.is_registration_profile)
    .sort((left, right) => (
      Number(right.is_promotional) - Number(left.is_promotional)
      || (left.display_name || left.mikrotik_profile).localeCompare(right.display_name || right.mikrotik_profile)
    ))
  const visiblePublishedPlans = publishedPlans.filter((profile) => (
    `${profile.display_name || ''} ${profile.mikrotik_profile}`.toLocaleLowerCase()
      .includes(planSearch.trim().toLocaleLowerCase())
  ))

  function edit(group = null) {
    setEditingId(group?.id || 'new')
    setForm(group ? {
      name: group.name,
      description: group.description || '',
      displayOrder: group.display_order,
      sortByPrice: group.sort_by_price,
      profileNames: group.profile_names || [],
    } : empty)
    setError('')
    setPlanSearch('')
  }

  function togglePlan(profileName) {
    setForm((current) => ({
      ...current,
      profileNames: current.profileNames.includes(profileName)
        ? current.profileNames.filter((name) => name !== profileName)
        : [...current.profileNames, profileName],
    }))
  }

  async function submit(event) {
    event.preventDefault()
    if (form.name.trim().length < 2) {
      setError('Enter a group name of at least 2 characters.')
      return
    }
    setSaving(true)
    setError('')
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      display_order: Number(form.displayOrder || 0),
      sort_by_price: form.sortByPrice,
      profile_names: form.profileNames,
    }
    try {
      if (editingId === 'new') await onCreate(payload)
      else await onUpdate(editingId, payload)
      setEditingId('')
      setForm(empty)
    } catch (saveError) {
      setError(saveError.message || 'The plan group could not be saved.')
    } finally { setSaving(false) }
  }

  async function remove(group) {
    const scope = bulkMode ? ' from every active hostel' : ''
    if (!window.confirm(`Delete the "${group.name}" group${scope}? Its plans will become ungrouped.`)) return
    try { await onDelete(group.id) } catch (deleteError) {
      setError(deleteError.message || 'The plan group could not be deleted.')
    }
  }

  return <section className="plan-groups-card">
    <header>
      <div><span className="dashboard-kicker">Customer organization</span><h3>{bulkMode ? 'All-hostel plan groups' : 'Plan groups'}</h3><p>{bulkMode ? 'Create and synchronize the same groups across every active hostel.' : 'Organize related plans into polished sections on the customer page.'}</p></div>
      {canEdit && !editingId && <button type="button" onClick={() => edit()}>+ Create group</button>}
    </header>
    {groups.length > 0 && <div className="plan-group-list">{groups.map((group) => <article key={group.id}>
      <div><strong>{group.name}</strong><p>{group.description || 'No description'}</p><small>{group.plan_count} plan{group.plan_count === 1 ? '' : 's'} &middot; {group.sort_by_price ? 'Lowest price first' : 'Plan name order'} &middot; position {group.display_order}{bulkMode ? ` · ${group.configured_hostels}/${group.hostel_count} hostels${group.settings_consistent ? '' : ' · needs synchronization'}` : ''}</small></div>
      {canEdit && <div><button type="button" onClick={() => edit(group)}>Manage plans</button><button className="danger" type="button" onClick={() => remove(group)}>Delete</button></div>}
    </article>)}</div>}
    {!groups.length && !editingId && <p className="plan-groups-empty">No groups yet. Plans continue to appear in the standard grid.</p>}
    {editingId && <form className="plan-group-form" onSubmit={submit}>
      <label><span>Group name</span><input autoFocus maxLength="120" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} placeholder="e.g. Daily bundles" /></label>
      <label><span>Description <em>Optional</em></span><input maxLength="500" value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} placeholder="Short customer-facing description" /></label>
      <div className="plan-group-form-row">
        <label><span>Group position</span><input min="0" required step="1" type="number" value={form.displayOrder} onChange={(event) => setForm((current) => ({ ...current, displayOrder: event.target.value }))} /></label>
        <label className="plan-group-price-sort"><input checked={form.sortByPrice} type="checkbox" onChange={(event) => setForm((current) => ({ ...current, sortByPrice: event.target.checked }))} /><span><strong>Order by increasing price</strong><small>Show the cheapest plan first inside this group.</small></span></label>
      </div>
      <section className="plan-group-plan-picker">
        <header><div><h4>Add published plans</h4><p>{bulkMode ? 'Only plans published across every active hostel are shown. Your selection will be synchronized everywhere.' : 'Select the plans that should appear in this group. Selecting a plan already in another group will move it here.'}</p></div><strong>{form.profileNames.length} selected</strong></header>
        {publishedPlans.length ? <>
          <div className="plan-group-picker-tools"><div className="profile-search"><Icon name="search" /><input aria-label="Search published plans" placeholder="Search published plans" type="search" value={planSearch} onChange={(event) => setPlanSearch(event.target.value)} /></div><button type="button" onClick={() => setForm((current) => ({ ...current, profileNames: publishedPlans.map((profile) => profile.mikrotik_profile) }))}>Select all</button><button type="button" onClick={() => setForm((current) => ({ ...current, profileNames: [] }))}>Clear</button></div>
          <div className="plan-group-plan-list">{visiblePublishedPlans.map((profile) => {
            const profileKey = profile.mikrotik_profile.toLocaleLowerCase()
            const currentGroup = bulkMode
              ? groups.find((group) => group.profile_names.some((name) => name.toLocaleLowerCase() === profileKey))
              : groups.find((group) => group.id === profile.group_id)
            return <label className="plan-group-plan-option" key={profile.mikrotik_profile}><input checked={form.profileNames.includes(profile.mikrotik_profile)} type="checkbox" onChange={() => togglePlan(profile.mikrotik_profile)} /><span><strong>{profile.display_name || titleFromProfile(profile.mikrotik_profile)}{profile.is_promotional && <em>Promo</em>}</strong><small>{profile.mikrotik_profile}{currentGroup && currentGroup.id !== editingId ? ` · currently in ${currentGroup.name}` : ''}</small></span><b>{formatMoney(profile.amount, profile.currency)}</b></label>
          })}</div>
          {!visiblePublishedPlans.length && <p className="plan-groups-empty">No published plans match your search.</p>}
        </> : <p className="plan-groups-empty">Publish a plan first, then return here to add it to this group.</p>}
      </section>
      {error && <div className="editor-error" role="alert"><Icon name="alert" />{error}</div>}
      <div className="plan-group-form-actions"><button type="button" onClick={() => { setEditingId(''); setError('') }}>Cancel</button><button disabled={saving} type="submit">{saving ? 'Saving...' : 'Save group'}</button></div>
    </form>}
  </section>
}

function MessagingPanel({ canEdit, hostels, onSessionExpired, embedded = false }) {
  const [form, setForm] = useState({ subject: '', message: '', routerId: '' })
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  function change(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }))
    setError('')
    setResult(null)
  }

  async function submit(event) {
    event.preventDefault()
    if (!form.subject.trim() || !form.message.trim()) {
      setError('Enter a subject and message.')
      return
    }
    const audience = form.routerId
      ? hostels.find((hostel) => hostel.router_id === form.routerId)?.name || 'the selected hostel'
      : 'all hostels'
    if (!window.confirm(`Send this message by SMS and email to users in ${audience}?`)) return
    setSending(true)
    setError('')
    try {
      setResult(await sendBroadcast(
        form.subject.trim(),
        form.message.trim(),
        form.routerId || null,
      ))
      setForm((current) => ({ ...current, subject: '', message: '' }))
    } catch (requestError) {
      if (requestError instanceof AdminApiError && requestError.status === 401) {
        onSessionExpired()
        return
      }
      setError('The message could not be sent. Check notification settings and try again.')
    } finally { setSending(false) }
  }

  return <>
    {!embedded && <header className="dashboard-page-heading"><div><p className="dashboard-kicker">Customer communications</p><h1>Send a service message</h1><p>Notify every customer, or only customers registered at one hostel. Use this for operational and account-related notices, not marketing without the required permission.</p></div></header>}
    <section className="support-settings-card">
      <header><span><Icon name="users" /></span><div><h2>New broadcast</h2><p>Messages are delivered by SMS to verified phones and by email.</p></div></header>
      <form onSubmit={submit}>
        <label><span>Recipients</span><select disabled={!canEdit || sending} name="routerId" value={form.routerId} onChange={change}><option value="">All users in all hostels</option>{hostels.map((hostel) => <option key={hostel.router_id} value={hostel.router_id}>Only {hostel.name}</option>)}</select></label>
        <label><span>Email subject</span><input disabled={!canEdit || sending} maxLength="120" name="subject" placeholder="Important Vlad WiFi update" value={form.subject} onChange={change} /></label>
        <label><span>Message</span><textarea disabled={!canEdit || sending} maxLength="1000" name="message" placeholder="Write your message here..." rows="7" value={form.message} onChange={change} /><small>{form.message.length}/1000 characters</small></label>
        {!canEdit && <div className="hostel-readonly-note"><Icon name="alert" />Your viewer role cannot send messages.</div>}
        {error && <div className="editor-error" role="alert"><Icon name="alert" />{error}</div>}
        {result && <div className="support-settings-success" role="status"><Icon name="check" />Targeted {result.targeted_users} users: {result.sms_sent} SMS and {result.email_sent} emails sent.{result.sms_failed + result.email_failed > 0 ? ` ${result.sms_failed + result.email_failed} deliveries failed.` : ''}</div>}
        {canEdit && <button className="support-settings-save" disabled={sending} type="submit">{sending ? 'Sending...' : 'Send message'}</button>}
      </form>
    </section>
  </>
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

function formatRevenue(amounts) {
  const entries = Object.entries(amounts || {})
  if (!entries.length) return formatMoney(0, 'GHS')
  return entries.map(([currency, amount]) => formatMoney(amount, currency)).join(' + ')
}

function formatDashboardTime(value) {
  if (!value) return ''
  return new Intl.DateTimeFormat('en-GH', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function formatStatus(value, fallback = 'Not started') {
  if (!value) return fallback
  return String(value).replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase())
}

function DashboardOverview({ hostels, loadingHostels, selectedId, onOpenCustomers, onOpenTransactions, onSelect, onSessionExpired }) {
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    if (loadingHostels) return undefined
    let active = true
    setLoading(true)
    setError('')
    getDashboard(selectedId && selectedId !== ALL_HOSTELS_ID ? selectedId : null)
      .then((result) => { if (active) setSummary(result) })
      .catch((requestError) => {
        if (!active) return
        if (requestError instanceof AdminApiError && requestError.status === 401) {
          onSessionExpired()
          return
        }
        setError('Dashboard information could not be loaded. Please try again.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [loadingHostels, selectedId, refreshKey])

  const unavailable = summary?.routers.filter((router) => !router.reachable) || []

  return <>
    <header className="dashboard-page-heading">
      <div><p className="dashboard-kicker">Live business overview</p><h1>Dashboard</h1><p>Customers, connected devices, revenue, and router health in one place.</p></div>
      <div className="dashboard-heading-actions">
        <div className="hostel-selector">
          <label htmlFor="dashboard-hostel-select">Hostel</label>
          <div><Icon name="building" /><select disabled={loadingHostels || !hostels.length} id="dashboard-hostel-select" value={selectedId || ALL_HOSTELS_ID} onChange={(event) => onSelect(event.target.value)}><option value={ALL_HOSTELS_ID}>All hostels</option>{hostels.map((hostel) => <option key={hostel.router_id} value={hostel.router_id}>{hostel.name}</option>)}</select></div>
        </div>
        <button aria-label="Refresh dashboard" className="dashboard-refresh-button" disabled={loading} type="button" onClick={() => setRefreshKey((value) => value + 1)}><Icon name="refresh" />{loading ? 'Refreshing' : 'Refresh'}</button>
      </div>
    </header>

    {error ? <div className="dashboard-load-error" role="alert"><Icon name="alert" /><div><strong>Unable to load dashboard</strong><p>{error}</p></div><button type="button" onClick={() => setRefreshKey((value) => value + 1)}>Try again</button></div> : loading && !summary ? <div className="dashboard-overview-loading"><span className="admin-page-spinner" /><p>Checking database totals and live routers...</p></div> : summary && <>
      {unavailable.length > 0 && <div className="router-warning" role="status"><Icon name="alert" /><div><strong>{unavailable.length === 1 ? `${unavailable[0].name} is unavailable` : `${unavailable.length} routers are unavailable`}</strong><p>Live user and device totals exclude unreachable routers. Database and revenue figures are still complete for the selected scope.</p></div></div>}

      <section className="dashboard-metric-grid" aria-label="Dashboard totals">
        <article className="dashboard-metric-primary"><span className="stat-icon"><Icon name="money" /></span><div><small>Revenue today</small><strong>{formatRevenue(summary.revenue.today)}</strong><p>{summary.revenue.successful_payments_today.toLocaleString()} successful transaction{summary.revenue.successful_payments_today === 1 ? '' : 's'}</p></div></article>
        <article><span className="stat-icon purple"><Icon name="users" /></span><div><small>Total users</small><strong>{summary.total_users.toLocaleString()}</strong><p>{summary.active_account_users.toLocaleString()} active accounts</p></div></article>
        <article><span className="stat-icon amber"><Icon name="clock" /></span><div><small>Active subscriptions</small><strong>{summary.active_subscriptions.toLocaleString()}</strong><p>Currently provisioned plans</p></div></article>
        <article><span className="stat-icon blue"><Icon name="device" /></span><div><small>Active devices</small><strong>{summary.active_devices.toLocaleString()}</strong><p>Live sessions for online users</p></div></article>
      </section>

      <div className="dashboard-detail-grid">
        <section className="dashboard-panel">
          <header><div><h2>Hostel status</h2><p>Live connection status by hostel</p></div><button type="button" onClick={onOpenCustomers}>View devices</button><span>{summary.routers.filter((router) => router.reachable).length}/{summary.routers.length} online</span></header>
          <div className="router-health-list">{summary.routers.length ? summary.routers.map((router) => <div key={router.router_id}><span className={`router-health-icon ${router.reachable ? 'online' : 'offline'}`}><Icon name={router.reachable ? 'wifi' : 'alert'} /></span><div><strong>{router.name}</strong><small>{router.reachable ? `${router.active_users} users · ${router.active_devices} devices` : router.error}</small></div><em className={router.reachable ? 'online' : 'offline'}>{router.reachable ? 'Online' : 'Unavailable'}</em></div>) : <p className="dashboard-empty-copy">No hostels are configured.</p>}</div>
        </section>

        <section className="dashboard-panel transactions-panel">
          <header><div><h2>Recent transactions</h2><p>Latest payments in this scope</p></div><button type="button" onClick={onOpenTransactions}>View all</button></header>
          <div className="recent-transaction-list">{summary.recent_transactions.length ? summary.recent_transactions.map((transaction) => <div key={transaction.reference}><span className={`transaction-mark ${transaction.status}`}><Icon name="receipt" /></span><div><strong>{transaction.package}</strong><small>{transaction.customer} · {formatDashboardTime(transaction.occurred_at)}</small></div><div className="transaction-amount"><strong>{formatMoney(transaction.amount, transaction.currency)}</strong><small className={transaction.status}>{transaction.status}</small></div></div>) : <p className="dashboard-empty-copy">No transactions yet.</p>}</div>
        </section>
      </div>
      <p className="dashboard-updated">Live figures checked {formatDashboardTime(summary.generated_at)}</p>
    </>}
  </>
}

const TRANSACTION_FILTER_DEFAULTS = {
  router_id: '',
  payment_status: '',
  date_range: 'all',
  date_from: '',
  date_to: '',
  search: '',
}

function dateInputValue(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function dateRangeValues(range) {
  if (!['last_7_days', 'last_30_days'].includes(range)) {
    return { date_from: '', date_to: '' }
  }
  const days = range === 'last_7_days' ? 7 : 30
  const end = new Date()
  const start = new Date(end)
  start.setDate(start.getDate() - (days - 1))
  return { date_from: dateInputValue(start), date_to: dateInputValue(end) }
}

function AccessPointCard({ ap, routerReachable }) {
  const status = !routerReachable ? 'Unknown' : ap.online ? 'Online' : 'Offline'
  return <article className={`ap-card ${status.toLowerCase()}`}>
    <header className="ap-card-heading"><span className="ap-device-icon"><Icon name="wifi" /></span><div><strong>{ap.host_name || `AP ${ap.ip_address.split('.').at(-1)}`}</strong><small>{ap.ip_address}</small></div><em><i />{status}</em></header>
    <div className="ap-card-details"><div><span><Icon name="network" /></span><p><small>Connected port</small><strong>{ap.connected_port || 'Port unknown'}</strong></p></div><div><span><Icon name="device" /></span><p><small>Active MAC</small><strong>{ap.active_mac || 'Not active'}</strong></p></div></div>
    {ap.configured_mac && ap.configured_mac !== ap.active_mac && <div className="ap-static-mac"><span>Static MAC</span><strong>{ap.configured_mac}</strong></div>}
    {ap.comment && <p className="ap-card-comment">{ap.comment}</p>}
    <footer><span>DHCP lease</span><strong>{ap.last_seen ? `Last seen ${ap.last_seen}` : ap.lease_status || 'Static'}</strong></footer>
  </article>
}

function AccessPointsPanel({ hostels, loadingHostels, selectedId, onSelect, onSessionExpired }) {
  const availableHostels = hostels.filter((hostel) => hostel.is_active)
  const hostelId = availableHostels.some((hostel) => hostel.router_id === selectedId) ? selectedId : availableHostels[0]?.router_id || ''
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [groupByPort, setGroupByPort] = useState(false)
  const knownPortCount = new Set(result?.access_points.map((ap) => ap.connected_port).filter(Boolean) || []).size
  const healthPercent = result?.access_points.length ? Math.round((result.online_count / result.access_points.length) * 100) : 0
  const portGroups = useMemo(() => {
    if (!result) return []
    const grouped = new Map()
    result.access_points.forEach((ap) => {
      const port = ap.connected_port || 'Port unknown'
      grouped.set(port, [...(grouped.get(port) || []), ap])
    })
    return [...grouped.entries()].sort(([left], [right]) => {
      if (left === 'Port unknown') return 1
      if (right === 'Port unknown') return -1
      return left.localeCompare(right, undefined, { numeric: true })
    })
  }, [result])

  useEffect(() => {
    if (!hostelId || loadingHostels) return undefined
    let active = true
    setLoading(true)
    setError('')
    getAccessPoints(hostelId)
      .then((data) => { if (active) setResult(data) })
      .catch((requestError) => {
        if (!active) return
        if (requestError instanceof AdminApiError && requestError.status === 401) return onSessionExpired()
        setError('Access point status could not be loaded. Please try again.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [hostelId, loadingHostels, refreshKey])

  function chooseHostel(event) {
    setResult(null)
    onSelect(event.target.value)
  }

  return <>
    <header className="dashboard-page-heading">
      <div><p className="dashboard-kicker">Hostel network</p><h1>Access points</h1><p>Live status for configured DHCP leases within the AP range, addresses .2 through .35.</p></div>
      <div className="dashboard-heading-actions">
        <div className="hostel-selector"><label htmlFor="ap-hostel-select">Selected hostel</label><div><Icon name="building" /><select disabled={loadingHostels || !availableHostels.length} id="ap-hostel-select" value={hostelId} onChange={chooseHostel}>{availableHostels.map((hostel) => <option key={hostel.router_id} value={hostel.router_id}>{hostel.name}</option>)}</select></div></div>
        <button className="dashboard-refresh-button" disabled={loading || !hostelId} type="button" onClick={() => setRefreshKey((value) => value + 1)}><Icon name="refresh" />{loading ? 'Checking' : 'Refresh'}</button>
      </div>
    </header>
    {!availableHostels.length && !loadingHostels ? <div className="profiles-empty"><Icon name="building" /><h3>No active hostels</h3><p>Add and activate a hostel before checking its access points.</p></div> : error ? <div className="dashboard-load-error" role="alert"><Icon name="alert" /><div><strong>Unable to load access points</strong><p>{error}</p></div><button type="button" onClick={() => setRefreshKey((value) => value + 1)}>Try again</button></div> : loading && !result ? <div className="dashboard-overview-loading"><span className="admin-page-spinner" /><p>Reading DHCP leases from the hostel router...</p></div> : result && <>
      {!result.router_reachable && <div className="router-warning" role="alert"><Icon name="alert" /><div><strong>Status unavailable</strong><p>{result.error} APs are not marked offline because the router itself could not be checked.</p></div></div>}
      <section className="ap-overview" aria-label="Access point overview">
        <article className="ap-health-card"><div className="ap-health-ring" style={{ '--health': `${result.router_reachable ? healthPercent : 0}%` }}><span>{result.router_reachable ? `${healthPercent}%` : '—'}</span></div><div><small>Network health</small><strong>{result.router_reachable ? (result.offline_count ? 'Attention needed' : 'All systems operational') : 'Router unavailable'}</strong><p>Based on active DHCP leases</p></div></article>
        <article className="ap-metric-card online"><span><Icon name="wifi" /></span><div><small>Online access points</small><strong>{result.online_count}</strong><p>Active MAC detected</p></div></article>
        <article className="ap-metric-card offline"><span><Icon name="alert" /></span><div><small>Offline access points</small><strong>{result.router_reachable ? result.offline_count : '—'}</strong><p>Configured, not active</p></div></article>
        <article className="ap-network-card"><span><Icon name="network" /></span><div><small>Network scope</small><strong>{result.network}</strong><p>{knownPortCount} active port{knownPortCount === 1 ? '' : 's'} detected</p></div><time dateTime={result.generated_at}>Updated {formatDashboardTime(result.generated_at)}</time></article>
      </section>
      <section className="ap-status-card">
        <header className="ap-list-header"><div><span className="ap-section-icon"><Icon name="network" /></span><div><h2>Access point inventory</h2><p>{result.hostel_name} · An AP is online when an active MAC is present.</p></div></div><div className="ap-view-controls"><div aria-label="Access point layout"><button aria-pressed={!groupByPort} className={!groupByPort ? 'active' : ''} type="button" onClick={() => setGroupByPort(false)}>All APs</button><button aria-pressed={groupByPort} className={groupByPort ? 'active' : ''} type="button" onClick={() => setGroupByPort(true)}>By port</button></div><span>{result.access_points.length} configured</span></div></header>
        {result.router_reachable && !result.access_points.length ? <div className="profiles-empty"><Icon name="network" /><h3>No access points configured</h3><p>No DHCP leases were found within addresses .2 through .35.</p></div> : groupByPort ? <div className="ap-port-groups">{portGroups.map(([port, accessPoints]) => <section key={port}><header><Icon name="network" /><h3>{port}</h3><span>{accessPoints.length} AP{accessPoints.length === 1 ? '' : 's'}</span></header><div className="ap-grid">{accessPoints.map((ap) => <AccessPointCard ap={ap} key={ap.ip_address} routerReachable={result.router_reachable} />)}</div></section>)}</div> : <div className="ap-grid">{result.access_points.map((ap) => <AccessPointCard ap={ap} key={ap.ip_address} routerReachable={result.router_reachable} />)}</div>}
      </section>
    </>}
  </>
}

function RevenueTransactionsPanel({ hostels, onSessionExpired }) {
  const [filters, setFilters] = useState(TRANSACTION_FILTER_DEFAULTS)
  const [appliedFilters, setAppliedFilters] = useState(TRANSACTION_FILTER_DEFAULTS)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    const queryFilters = { ...appliedFilters, limit: 100 }
    delete queryFilters.date_range
    getTransactions(queryFilters)
      .then((data) => { if (active) setResult(data) })
      .catch((requestError) => {
        if (!active) return
        if (requestError instanceof AdminApiError && requestError.status === 401) {
          onSessionExpired()
          return
        }
        setError('Revenue and transaction information could not be loaded.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [appliedFilters, refreshKey])

  function change(event) {
    setFilters((current) => ({
      ...current,
      [event.target.name]: event.target.value,
      ...(['date_from', 'date_to'].includes(event.target.name) ? { date_range: 'custom' } : {}),
    }))
  }

  function apply(event) {
    event.preventDefault()
    setAppliedFilters({ ...filters })
  }

  function clearFilters() {
    setFilters(TRANSACTION_FILTER_DEFAULTS)
    setAppliedFilters(TRANSACTION_FILTER_DEFAULTS)
  }

  function chooseDateRange(range) {
    if (range === 'custom') {
      setFilters((current) => ({ ...current, date_range: 'custom' }))
      return
    }
    const next = { ...filters, date_range: range, ...dateRangeValues(range) }
    setFilters(next)
    setAppliedFilters(next)
  }

  const leadingPlan = result?.plan_revenue.find((plan) => Number(plan.successful_revenue) > 0)

  return <>
    <header className="dashboard-page-heading">
      <div><p className="dashboard-kicker">Financial performance</p><h1>Revenue &amp; transactions</h1><p>Review revenue by plan and hostel alongside payment outcomes and individual transaction records.</p></div>
      <button className="dashboard-refresh-button" disabled={loading} type="button" onClick={() => setRefreshKey((value) => value + 1)}><Icon name="refresh" />{loading ? 'Refreshing' : 'Refresh'}</button>
    </header>

    <div className="revenue-date-presets" aria-label="Revenue date range">
      <span>Date range</span>
      <div>{[
        ['all', 'All time'],
        ['last_7_days', 'Last 7 days'],
        ['last_30_days', 'Last 30 days'],
        ['custom', 'Custom'],
      ].map(([value, label]) => <button aria-pressed={filters.date_range === value} className={filters.date_range === value ? 'active' : ''} key={value} type="button" onClick={() => chooseDateRange(value)}>{label}</button>)}</div>
    </div>

    <form className={`admin-data-filters ${filters.date_range === 'custom' ? '' : 'revenue-filters-compact'}`} onSubmit={apply}>
      <label><span>Hostel</span><select name="router_id" value={filters.router_id} onChange={change}><option value="">All hostels</option>{hostels.map((hostel) => <option key={hostel.router_id} value={hostel.router_id}>{hostel.name}</option>)}</select></label>
      <label><span>Payment status</span><select name="payment_status" value={filters.payment_status} onChange={change}><option value="">All statuses</option><option value="success">Successful</option><option value="pending">Pending</option><option value="failed">Failed</option></select></label>
      {filters.date_range === 'custom' && <><label><span>From</span><input name="date_from" type="date" value={filters.date_from} onChange={change} /></label><label><span>To</span><input name="date_to" type="date" value={filters.date_to} onChange={change} /></label></>}
      <label className="admin-filter-search"><span>Search</span><input name="search" placeholder="Reference, user, email or plan" type="search" value={filters.search} onChange={change} /></label>
      <div><button type="button" onClick={clearFilters}>Clear</button><button className="primary" type="submit">Apply filters</button></div>
    </form>

    {error && <div className="dashboard-load-error" role="alert"><Icon name="alert" /><div><strong>Unable to load transactions</strong><p>{error}</p></div></div>}
    {loading && !result ? <div className="dashboard-overview-loading"><span className="admin-page-spinner" /><p>Loading financial records...</p></div> : result && <>
      <section className="dashboard-metric-grid admin-data-metrics">
        <article><span className="stat-icon green"><Icon name="money" /></span><div><small>Filtered revenue</small><strong>{formatRevenue(result.revenue)}</strong><p>Successful transactions only</p></div></article>
        <article><span className="stat-icon purple"><Icon name="check" /></span><div><small>Successful</small><strong>{result.successful.toLocaleString()}</strong><p>Completed payments and free claims</p></div></article>
        <article><span className="stat-icon amber"><Icon name="clock" /></span><div><small>Pending</small><strong>{result.pending.toLocaleString()}</strong><p>Awaiting payment or verification</p></div></article>
        <article><span className="stat-icon blue"><Icon name="alert" /></span><div><small>Failed</small><strong>{result.failed.toLocaleString()}</strong><p>Unsuccessful payment attempts</p></div></article>
      </section>

      <section className="admin-data-card profile-performance-card">
        <header><div><h2>Revenue by plan</h2><p>Revenue generated by each plan for the selected hostel and date filters. Plans with no sales remain visible.</p></div>{leadingPlan && <span className="performance-leader"><Icon name="tag" /><small>Top revenue plan</small><strong>{leadingPlan.display_name}</strong></span>}</header>
        <div className="admin-data-table-wrap"><table className="admin-data-table plan-revenue-table"><thead><tr><th>Plan</th><th>Successful revenue</th><th>Successful sales</th><th>Share of revenue</th><th>Availability</th></tr></thead><tbody>
          {result.plan_revenue.map((plan) => <tr key={`${plan.profile}-${plan.currency}`}>
            <td><strong>{plan.display_name}</strong><small>RouterOS profile: {plan.profile}</small></td>
            <td><strong>{formatMoney(plan.successful_revenue, plan.currency)}</strong></td>
            <td><strong>{plan.successful_sales.toLocaleString()}</strong><small>Completed payments and free claims</small></td>
            <td><div className="performance-rate"><span><i style={{ width: `${plan.revenue_share_percent}%` }} /></span><strong>{Number(plan.revenue_share_percent).toFixed(1)}%</strong></div></td>
            <td><strong>{plan.hostel_count} hostel{plan.hostel_count === 1 ? '' : 's'}</strong></td>
          </tr>)}
        </tbody></table>{!result.plan_revenue.length && <p className="dashboard-empty-copy">No configured plans are available in this hostel scope.</p>}</div>
      </section>

      {!appliedFilters.router_id && <section className="admin-data-card hostel-revenue-card">
        <header><div><h2>Revenue by hostel</h2><p>How much each hostel generated for the selected date and payment filters.</p></div></header>
        <div className="hostel-revenue-grid">{result.hostel_revenue.map((hostel) => <article key={hostel.hostel_id}><span><Icon name="building" /></span><div><small>{hostel.hostel_name}</small><strong>{formatRevenue(hostel.revenue)}</strong><p>{hostel.successful_sales.toLocaleString()} successful sale{hostel.successful_sales === 1 ? '' : 's'}</p></div></article>)}</div>
      </section>}

      <section className="admin-data-card">
        <header><div><h2>Transactions</h2><p>{result.total.toLocaleString()} record{result.total === 1 ? '' : 's'} match the current filters. Showing up to 100 newest.</p></div></header>
        <div className="admin-data-table-wrap"><table className="admin-data-table"><thead><tr><th>Customer</th><th>Plan / hostel</th><th>Amount</th><th>Payment</th><th>Activation</th><th>Date</th><th>Reference</th></tr></thead><tbody>
          {result.transactions.map((transaction) => <tr key={transaction.reference}>
            <td><strong>{transaction.customer_username}</strong><small>{transaction.customer_email}</small>{transaction.customer_phone && <small>{transaction.customer_phone}</small>}</td>
            <td><strong>{transaction.package}</strong><small>{transaction.hostel_name}</small></td>
            <td><strong>{Number(transaction.amount) === 0 ? 'Free' : formatMoney(transaction.amount, transaction.currency)}</strong></td>
            <td><span className={`admin-status-pill ${transaction.status}`}>{formatStatus(transaction.status)}</span><small>{formatStatus(transaction.provider_status, 'No provider status')}</small></td>
            <td><span className={`admin-status-pill ${transaction.activation_status || 'pending'}`}>{formatStatus(transaction.activation_status)}</span></td>
            <td><strong>{formatDashboardTime(transaction.occurred_at)}</strong></td>
            <td><code>{transaction.reference}</code></td>
          </tr>)}
        </tbody></table>{!result.transactions.length && <p className="dashboard-empty-copy">No transactions match these filters.</p>}</div>
      </section>
    </>}
  </>
}

const CUSTOMER_FILTER_DEFAULTS = {
  router_id: '',
  account_status: '',
  subscription: 'all',
  search: '',
}

function CustomersDevicesPanel({ admin, hostels, onSessionExpired }) {
  const [mode, setMode] = useState('customers')
  const [filters, setFilters] = useState(CUSTOMER_FILTER_DEFAULTS)
  const [appliedFilters, setAppliedFilters] = useState(CUSTOMER_FILTER_DEFAULTS)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [customerAction, setCustomerAction] = useState(null)
  const [actionForm, setActionForm] = useState({ destinationRouterId: '', password: '' })
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [actionSuccess, setActionSuccess] = useState('')

  useEffect(() => {
    if (!customerAction) return undefined

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    function closeOnEscape(event) {
      if (event.key === 'Escape' && !actionBusy) {
        setCustomerAction(null)
        setActionForm({ destinationRouterId: '', password: '' })
        setActionError('')
      }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [customerAction, actionBusy])

  useEffect(() => {
    if (mode === 'message') return undefined
    let active = true
    setLoading(true)
    setError('')
    getCustomersAndDevices({ ...appliedFilters, limit: 200 })
      .then((data) => { if (active) setResult(data) })
      .catch((requestError) => {
        if (!active) return
        if (requestError instanceof AdminApiError && requestError.status === 401) {
          onSessionExpired()
          return
        }
        setError('Customer and live device information could not be loaded.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [appliedFilters, mode, refreshKey])

  function change(event) {
    setFilters((current) => ({ ...current, [event.target.name]: event.target.value }))
  }

  function apply(event) {
    event.preventDefault()
    setAppliedFilters({ ...filters })
  }

  function openCustomerAction(customer, action) {
    setCustomerAction({ customer, action })
    setActionForm({ destinationRouterId: '', password: '' })
    setActionError('')
    setActionSuccess('')
  }

  function closeCustomerAction() {
    if (actionBusy) return
    setCustomerAction(null)
    setActionForm({ destinationRouterId: '', password: '' })
    setActionError('')
  }

  async function submitCustomerAction(event) {
    event.preventDefault()
    if (!customerAction || actionBusy) return
    if (actionForm.password.length < 8) {
      setActionError('Enter your admin password to confirm this action.')
      return
    }
    if (customerAction.action === 'transfer' && !actionForm.destinationRouterId) {
      setActionError('Select the customer’s new hostel.')
      return
    }
    setActionBusy(true)
    setActionError('')
    try {
      if (customerAction.action === 'delete') {
        await deleteCustomer(customerAction.customer.id, actionForm.password)
        setActionSuccess(`${customerAction.customer.username} was permanently deleted.`)
      } else {
        const transferred = await transferCustomerHostel(
          customerAction.customer.id,
          actionForm.destinationRouterId,
          actionForm.password,
        )
        setActionSuccess(`${customerAction.customer.username} was moved to ${transferred.hostel_name}.`)
      }
      setCustomerAction(null)
      setActionForm({ destinationRouterId: '', password: '' })
      setRefreshKey((value) => value + 1)
    } catch (requestError) {
      if (requestError instanceof AdminApiError && requestError.status === 401) {
        try {
          await getAdminSession()
        } catch {
          onSessionExpired()
          return
        }
        setActionError('The admin password is incorrect. No changes were made.')
      } else if (requestError instanceof AdminApiError && requestError.status === 409) {
        setActionError('The action cannot be completed. For a transfer, confirm the plan exists at the new hostel and the username is available there.')
      } else if (requestError instanceof AdminApiError && [502, 503].includes(requestError.status)) {
        setActionError('A hostel router is unavailable. The action was not completed.')
      } else {
        setActionError('The customer action could not be completed. Please try again.')
      }
    } finally {
      setActionBusy(false)
    }
  }

  return <>
    <header className="dashboard-page-heading">
      <div><p className="dashboard-kicker">Customer operations</p><h1>Customers &amp; devices</h1><p>Understand account status, subscriptions, live connections, and communicate with your users.</p></div>
      {mode !== 'message' && <button className="dashboard-refresh-button" disabled={loading} type="button" onClick={() => setRefreshKey((value) => value + 1)}><Icon name="refresh" />{loading ? 'Refreshing' : 'Refresh live data'}</button>}
    </header>

    <div className="admin-section-tabs" role="tablist" aria-label="Customer information"><button className={mode === 'customers' ? 'active' : ''} role="tab" type="button" onClick={() => setMode('customers')}><Icon name="users" />Users</button><button className={mode === 'devices' ? 'active' : ''} role="tab" type="button" onClick={() => setMode('devices')}><Icon name="device" />Connected devices</button><button className={mode === 'message' ? 'active' : ''} role="tab" type="button" onClick={() => setMode('message')}><Icon name="activity" />Message users</button></div>

    {mode === 'message' ? <MessagingPanel embedded canEdit={admin.role !== 'viewer'} hostels={hostels} onSessionExpired={onSessionExpired} /> : <>
      <form className="admin-data-filters customer-filters" onSubmit={apply}>
        <label><span>Hostel</span><select name="router_id" value={filters.router_id} onChange={change}><option value="">All hostels</option>{hostels.map((hostel) => <option key={hostel.router_id} value={hostel.router_id}>{hostel.name}</option>)}</select></label>
        <label><span>Account status</span><select name="account_status" value={filters.account_status} onChange={change}><option value="">All accounts</option><option value="active">Active</option><option value="inactive">Inactive</option><option value="suspended">Suspended</option><option value="closed">Closed</option></select></label>
        <label><span>Subscription</span><select name="subscription" value={filters.subscription} onChange={change}><option value="all">All users</option><option value="active">Active plan</option><option value="inactive">No active plan</option></select></label>
        <label className="admin-filter-search"><span>Search</span><input name="search" placeholder="Username, email or phone" type="search" value={filters.search} onChange={change} /></label>
        <div><button type="button" onClick={() => { setFilters(CUSTOMER_FILTER_DEFAULTS); setAppliedFilters(CUSTOMER_FILTER_DEFAULTS) }}>Clear</button><button className="primary" type="submit">Apply filters</button></div>
      </form>

      {actionSuccess && <div className="customer-action-notice success" role="status"><Icon name="check" />{actionSuccess}</div>}
      {customerAction && <div className="admin-modal-backdrop" role="presentation" onMouseDown={closeCustomerAction}>
        <section className={`customer-action-panel ${customerAction.action === 'delete' ? 'danger' : ''}`} role="dialog" aria-modal="true" aria-labelledby="customer-action-title" onMouseDown={(event) => event.stopPropagation()}>
          <header><div><span className="customer-action-kicker">Password confirmation required</span><h2 id="customer-action-title">{customerAction.action === 'delete' ? `Delete ${customerAction.customer.username}?` : `Move ${customerAction.customer.username}?`}</h2><p>{customerAction.action === 'delete' ? 'This permanently removes the account, history, web sessions, RouterOS user, active WiFi sessions, and remembered cookies. This cannot be undone.' : `The RouterOS account will move from ${customerAction.customer.hostel_name}. Active sessions and cookies will be removed, and used data will be deducted first.`}</p></div><button aria-label="Close customer action" disabled={actionBusy} type="button" onClick={closeCustomerAction}><Icon name="close" /></button></header>
          <form noValidate onSubmit={submitCustomerAction}>
            {customerAction.action === 'transfer' && <label><span>New hostel</span><select autoFocus value={actionForm.destinationRouterId} onChange={(event) => { setActionForm((current) => ({ ...current, destinationRouterId: event.target.value })); setActionError('') }}><option value="">Select destination</option>{hostels.filter((hostel) => hostel.is_active && hostel.router_id !== customerAction.customer.hostel_id).map((hostel) => <option key={hostel.router_id} value={hostel.router_id}>{hostel.name}</option>)}</select></label>}
            <label><span>Admin password</span><input autoFocus={customerAction.action === 'delete'} autoComplete="current-password" maxLength={128} minLength={8} placeholder="Enter your password" type="password" value={actionForm.password} onChange={(event) => { setActionForm((current) => ({ ...current, password: event.target.value })); setActionError('') }} /></label>
            {actionError && <p role="alert">{actionError}</p>}
            <div><button disabled={actionBusy} type="button" onClick={closeCustomerAction}>Cancel</button><button className="primary" disabled={actionBusy} type="submit">{actionBusy ? 'Working...' : customerAction.action === 'delete' ? 'Delete permanently' : 'Confirm hostel move'}</button></div>
          </form>
        </section>
      </div>}

      {result?.unavailable_routers.length > 0 && <div className="router-warning"><Icon name="alert" /><div><strong>Some live data is unavailable</strong><p>{result.unavailable_routers.join(', ')} could not be reached. Stored customer information is still shown.</p></div></div>}
      {error && <div className="dashboard-load-error" role="alert"><Icon name="alert" /><div><strong>Unable to load customer information</strong><p>{error}</p></div></div>}
      {loading && !result ? <div className="dashboard-overview-loading"><span className="admin-page-spinner" /><p>Loading customers and checking connected devices...</p></div> : result && <>
        <section className="dashboard-metric-grid admin-data-metrics"><article><span className="stat-icon purple"><Icon name="users" /></span><div><small>Total users</small><strong>{result.total_users.toLocaleString()}</strong><p>{result.matched_users.toLocaleString()} match the filters</p></div></article><article><span className="stat-icon amber"><Icon name="clock" /></span><div><small>Active subscriptions</small><strong>{result.active_subscriptions.toLocaleString()}</strong><p>Across the selected hostel scope</p></div></article><article><span className="stat-icon green"><Icon name="wifi" /></span><div><small>Online users</small><strong>{result.online_users.toLocaleString()}</strong><p>Currently visible on RouterOS</p></div></article><article><span className="stat-icon blue"><Icon name="device" /></span><div><small>Active devices</small><strong>{result.active_devices.toLocaleString()}</strong><p>Live HotSpot sessions</p></div></article></section>

        <section className="admin-data-card"><header><div><h2>{mode === 'customers' ? 'User directory' : 'Connected devices'}</h2><p>{mode === 'customers' ? `Showing up to 200 of ${result.matched_users.toLocaleString()} matching users.` : 'Live sessions reported by reachable hostel routers.'}</p></div></header><div className="admin-data-table-wrap">
          {mode === 'customers' ? <table className="admin-data-table"><thead><tr><th>User</th><th>Contact</th><th>Hostel</th><th>Account</th><th>Current plan</th><th>Connection</th><th>Last activity</th>{admin.role !== 'viewer' && <th>Actions</th>}</tr></thead><tbody>{result.customers.map((customer) => <tr key={customer.id}><td><strong>{customer.username}</strong><small>Joined {formatDashboardTime(customer.joined_at)}</small></td><td><strong>{customer.email}</strong><small>{customer.phone_number || 'No phone number'}{customer.phone_verified ? ' · verified' : ''}</small></td><td><strong>{customer.hostel_name}</strong></td><td><span className={`admin-status-pill ${customer.account_status}`}>{formatStatus(customer.account_status)}</span></td><td><strong>{customer.current_plan || 'No active plan'}</strong><small>{formatStatus(customer.subscription_status, 'No subscription')}</small></td><td><span className={`admin-status-pill ${customer.is_online ? 'success' : 'offline'}`}>{customer.is_online ? 'Online' : 'Offline'}</span><small>{customer.connected_devices} device{customer.connected_devices === 1 ? '' : 's'}</small></td><td><strong>{formatDashboardTime(customer.last_activity_at)}</strong><small>{customer.last_login_at ? `Last login ${formatDashboardTime(customer.last_login_at)}` : 'Never logged in'}</small></td>{admin.role !== 'viewer' && <td><div className="customer-row-actions"><button type="button" onClick={() => openCustomerAction(customer, 'transfer')}>Move</button><button className="danger" type="button" onClick={() => openCustomerAction(customer, 'delete')}>Delete</button></div></td>}</tr>)}</tbody></table> : <table className="admin-data-table"><thead><tr><th>User</th><th>Hostel</th><th>IP address</th><th>MAC address</th><th>Uptime</th><th>Login method</th></tr></thead><tbody>{result.devices.map((device) => <tr key={`${device.hostel_id}-${device.session_id}`}><td><strong>{device.username}</strong><small>{device.customer_email || 'Not linked to a customer record'}</small></td><td><strong>{device.hostel_name}</strong></td><td><code>{device.ip_address || '--'}</code></td><td><code>{device.mac_address || '--'}</code></td><td><strong>{device.uptime || '--'}</strong></td><td><strong>{formatStatus(device.login_method, '--')}</strong></td></tr>)}</tbody></table>}
          {mode === 'customers' && !result.customers.length && <p className="dashboard-empty-copy">No users match these filters.</p>}{mode === 'devices' && !result.devices.length && <p className="dashboard-empty-copy">No connected devices match these filters.</p>}
        </div></section>
      </>}
    </>}
  </>
}

export default function AdminDashboard({ admin, onSessionExpired }) {
  const [view, setView] = useState('dashboard')
  const [hostels, setHostels] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [profiles, setProfiles] = useState([])
  const [planGroups, setPlanGroups] = useState([])
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [showProfileMenu, setShowProfileMenu] = useState(false)
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)

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

  useEffect(() => {
    if (!mobileSidebarOpen && !showProfileMenu && !showLogoutConfirm) return undefined

    const previousOverflow = document.body.style.overflow
    if (mobileSidebarOpen || showLogoutConfirm) document.body.style.overflow = 'hidden'
    function closeOnEscape(event) {
      if (event.key !== 'Escape' || signingOut) return
      if (showLogoutConfirm) setShowLogoutConfirm(false)
      else if (showProfileMenu) setShowProfileMenu(false)
      else setMobileSidebarOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [mobileSidebarOpen, showProfileMenu, showLogoutConfirm, signingOut])

  function toggleSidebar() {
    if (window.matchMedia('(max-width: 760px)').matches) {
      setMobileSidebarOpen((current) => !current)
      return
    }
    setSidebarCollapsed((current) => !current)
  }

  function closeOrCollapseSidebar() {
    if (window.matchMedia('(max-width: 760px)').matches) {
      setMobileSidebarOpen(false)
      return
    }
    setSidebarCollapsed((current) => !current)
  }

  function selectView(nextView) {
    setView(nextView)
    setMobileSidebarOpen(false)
  }

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
        setSelectedId((current) => current || ALL_HOSTELS_ID)
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

  useEffect(() => {
    if (!selectedId || view !== 'profiles') {
      setPlanGroups([])
      return undefined
    }
    let active = true
    const request = selectedId === ALL_HOSTELS_ID
      ? listAllHostelPlanGroups()
      : listPlanGroups(selectedId)
    request
      .then((items) => { if (active) setPlanGroups(items) })
      .catch((error) => handleError(error, 'Plan groups could not be loaded.'))
    return () => { active = false }
  }, [selectedId, view])

  async function addPlanGroup(payload) {
    try {
      const created = allHostelsSelected
        ? await createAllHostelPlanGroup(payload)
        : await createPlanGroup(selectedId, payload)
      setPlanGroups((current) => [...current, created]
        .sort((left, right) => left.display_order - right.display_order || left.name.localeCompare(right.name)))
      if (!allHostelsSelected) {
        setProfiles((current) => current.map((profile) => (
          payload.profile_names.includes(profile.mikrotik_profile)
            ? { ...profile, group_id: created.id }
            : profile
        )))
      }
      try {
        setPlanGroups(allHostelsSelected
          ? await listAllHostelPlanGroups()
          : await listPlanGroups(selectedId))
      } catch (refreshError) {
        if (refreshError instanceof AdminApiError && refreshError.status === 401) onSessionExpired()
      }
      setToast(allHostelsSelected ? 'Plan group created across all active hostels.' : 'Plan group created.')
    } catch (error) {
      if (error instanceof AdminApiError && error.status === 401) onSessionExpired()
      throw new Error(error instanceof AdminApiError && error.status === 409 ? 'A group with that name already exists.' : 'The plan group could not be created.')
    }
  }

  async function editPlanGroup(groupId, payload) {
    try {
      const updated = allHostelsSelected
        ? await updateAllHostelPlanGroup(groupId, payload)
        : await updatePlanGroup(selectedId, groupId, payload)
      setPlanGroups((current) => current.map((group) => group.id === groupId ? updated : group)
        .sort((left, right) => left.display_order - right.display_order || left.name.localeCompare(right.name)))
      if (!allHostelsSelected) {
        setProfiles((current) => current.map((profile) => {
          if (payload.profile_names.includes(profile.mikrotik_profile)) {
            return { ...profile, group_id: groupId }
          }
          return profile.group_id === groupId ? { ...profile, group_id: null } : profile
        }))
      }
      try {
        setPlanGroups(allHostelsSelected
          ? await listAllHostelPlanGroups()
          : await listPlanGroups(selectedId))
      } catch (refreshError) {
        if (refreshError instanceof AdminApiError && refreshError.status === 401) onSessionExpired()
      }
      setToast(allHostelsSelected ? 'Plan group synchronized across all active hostels.' : 'Plan group updated.')
    } catch (error) {
      if (error instanceof AdminApiError && error.status === 401) onSessionExpired()
      throw new Error(error instanceof AdminApiError && error.status === 409 ? 'A group with that name already exists.' : 'The plan group could not be updated.')
    }
  }

  async function removePlanGroup(groupId) {
    try {
      if (allHostelsSelected) await deleteAllHostelPlanGroup(groupId)
      else await deletePlanGroup(selectedId, groupId)
      setPlanGroups((current) => current.filter((group) => group.id !== groupId))
      if (!allHostelsSelected) {
        setProfiles((current) => current.map((profile) => profile.group_id === groupId ? { ...profile, group_id: null } : profile))
      }
      setToast(allHostelsSelected ? 'Plan group deleted from all active hostels.' : 'Plan group deleted; its plans are now ungrouped.')
    } catch (error) {
      if (error instanceof AdminApiError && error.status === 401) onSessionExpired()
      throw new Error('The plan group could not be deleted.')
    }
  }

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
    try { setPlanGroups(await listPlanGroups(selectedId)) } catch (error) {
      if (error instanceof AdminApiError && error.status === 401) onSessionExpired()
    }
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
    if (!allHostelsSelected) {
      try { setPlanGroups(await listPlanGroups(selectedId)) } catch (error) {
        if (error instanceof AdminApiError && error.status === 401) onSessionExpired()
      }
    }
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
    <div className={`admin-dashboard${sidebarCollapsed ? ' sidebar-collapsed' : ''}`}>
      {mobileSidebarOpen && <button className="dashboard-sidebar-backdrop" type="button" aria-label="Close navigation" onClick={() => setMobileSidebarOpen(false)} />}
      <aside className={`dashboard-sidebar${mobileSidebarOpen ? ' mobile-open' : ''}`}>
        <div className="dashboard-sidebar-header">
          <Brand />
          <button className="dashboard-sidebar-toggle" type="button" aria-label={sidebarCollapsed ? 'Expand navigation' : 'Collapse navigation'} onClick={closeOrCollapseSidebar}><span className="desktop-sidebar-back"><Icon name="back" /></span><span className="desktop-sidebar-menu"><Icon name="menu" /></span><span className="mobile-sidebar-close"><Icon name="close" /></span></button>
        </div>
        <nav aria-label="Admin navigation">
          <p>Workspace</p>
          <button aria-label="Dashboard" className={view === 'dashboard' ? 'active' : ''} title="Dashboard" type="button" onClick={() => selectView('dashboard')}><Icon name="grid" /><span className="sidebar-nav-label">Dashboard</span></button>
          <button aria-label="Hostels" className={view === 'hostels' ? 'active' : ''} title="Hostels" type="button" onClick={() => selectView('hostels')}><Icon name="building" /><span className="sidebar-nav-label">Hostels</span></button>
          <button aria-label="Profile catalogue" className={view === 'profiles' ? 'active' : ''} title="Profile catalogue" type="button" onClick={() => selectView('profiles')}><Icon name="tag" /><span className="sidebar-nav-label">Profile catalogue</span></button>
          <p>Management</p>
          <button aria-label="Customers and devices" className={view === 'customers' ? 'active' : ''} title="Customers & devices" type="button" onClick={() => selectView('customers')}><Icon name="users" /><span className="sidebar-nav-label">Customers &amp; devices</span></button>
          <button aria-label="Access points" className={view === 'network' ? 'active' : ''} title="Access points" type="button" onClick={() => selectView('network')}><Icon name="network" /><span className="sidebar-nav-label">Access points</span></button>
          <button aria-label="Revenue and transactions" className={view === 'transactions' ? 'active' : ''} title="Revenue & transactions" type="button" onClick={() => selectView('transactions')}><Icon name="receipt" /><span className="sidebar-nav-label">Revenue &amp; transactions</span></button>
          <button aria-label="Help and support" className={view === 'support' ? 'active' : ''} title="Help & support" type="button" onClick={() => selectView('support')}><Icon name="settings" /><span className="sidebar-nav-label">Help &amp; support</span></button>
        </nav>
        <div className="sidebar-security"><span><Icon name="check" /></span><div><strong>Secure session</strong><small>Protected admin access</small></div></div>
      </aside>

      <main className="dashboard-main">
        <header className="dashboard-topbar">
          <div className="dashboard-topbar-start">
            <button className="dashboard-menu-button" type="button" aria-label={mobileSidebarOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={mobileSidebarOpen} onClick={toggleSidebar}><Icon name="menu" /></button>
            <div className="mobile-dashboard-brand"><Brand /></div>
          </div>
          <div className="dashboard-admin-menu">
            <button className="admin-profile-trigger" type="button" aria-haspopup="menu" aria-expanded={showProfileMenu} onClick={() => setShowProfileMenu((current) => !current)}>
              <span className="admin-avatar">{admin.username.slice(0, 1).toUpperCase()}</span>
              <span className="admin-profile-copy"><strong>{admin.username}</strong><small>{admin.role}</small></span>
              <Icon name="chevron" />
            </button>
            {showProfileMenu && <>
              <button className="admin-profile-menu-backdrop" type="button" aria-label="Close account menu" onClick={() => setShowProfileMenu(false)} />
              <div className="admin-profile-dropdown" role="menu">
                <div className="admin-profile-dropdown-heading"><span className="admin-avatar">{admin.username.slice(0, 1).toUpperCase()}</span><div><strong>{admin.username}</strong><small>{admin.role}</small></div></div>
                <div className="admin-profile-session"><Icon name="check" /><span><strong>Secure session</strong><small>Protected admin access</small></span></div>
                <button role="menuitem" disabled={signingOut} type="button" onClick={() => { setShowProfileMenu(false); setShowLogoutConfirm(true) }}><Icon name="logout" /><span>Log out</span></button>
              </div>
            </>}
          </div>
        </header>

        <div className="dashboard-content">
          {view === 'dashboard' ? <DashboardOverview hostels={hostels} loadingHostels={loadingHostels} selectedId={selectedId} onOpenCustomers={() => setView('customers')} onOpenTransactions={() => setView('transactions')} onSelect={setSelectedId} onSessionExpired={onSessionExpired} /> : view === 'customers' ? <CustomersDevicesPanel admin={admin} hostels={hostels} onSessionExpired={onSessionExpired} /> : view === 'network' ? <AccessPointsPanel hostels={hostels} loadingHostels={loadingHostels} selectedId={selectedId} onSelect={setSelectedId} onSessionExpired={onSessionExpired} /> : view === 'transactions' ? <RevenueTransactionsPanel hostels={hostels} onSessionExpired={onSessionExpired} /> : view === 'support' ? <SupportSettingsPanel canEdit={admin.role !== 'viewer'} onSessionExpired={onSessionExpired} /> : view === 'hostels' ? <>
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

            {selectedHostel && (
              <PlanGroupManager
                bulkMode={allHostelsSelected}
                canEdit={admin.role !== 'viewer'}
                groups={planGroups}
                onCreate={addPlanGroup}
                onDelete={removePlanGroup}
                onUpdate={editPlanGroup}
                profiles={profiles}
              />
            )}

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

      {editingProfile && selectedHostel && <ProfileEditor groups={planGroups} hostel={selectedHostel} profile={editingProfile} onClose={() => setEditingProfile(null)} onDelete={deleteProfileConfiguration} onSave={saveProfile} />}
      {viewingHostel === 'details' && selectedHostel && <HostelEditor canEdit={admin.role !== 'viewer'} hostel={selectedHostel} onClose={() => setViewingHostel(false)} onSave={saveHostel} />}
      {viewingHostel === 'new' && <HostelEditor canEdit hostel={null} onClose={() => setViewingHostel(false)} onSave={addHostel} />}
      {showLogoutConfirm && <div className="admin-modal-backdrop" role="presentation" onMouseDown={() => !signingOut && setShowLogoutConfirm(false)}>
        <section className="admin-logout-modal" role="dialog" aria-modal="true" aria-labelledby="admin-logout-title" onMouseDown={(event) => event.stopPropagation()}>
          <span className="admin-logout-modal-icon"><Icon name="logout" /></span>
          <h2 id="admin-logout-title">Log out of the admin console?</h2>
          <p>Your secure admin session will end and you will need to enter your credentials again.</p>
          <div><button disabled={signingOut} type="button" onClick={() => setShowLogoutConfirm(false)}>Stay signed in</button><button className="confirm-logout" disabled={signingOut} type="button" onClick={signOut}>{signingOut ? 'Logging out...' : 'Yes, log out'}</button></div>
        </section>
      </div>}
      {toast && <div className="dashboard-toast" role="status"><Icon name="check" />{toast}</div>}
    </div>
  )
}
