import { useEffect, useMemo, useState } from 'react'

import {
  AdminApiError,
  createHostel,
  listHostelProfiles,
  listHostels,
  logout,
  saveHostelProfile,
  updateHostel,
} from '../services/adminApi'

const DURATION_UNITS = {
  hours: 60 * 60,
  days: 24 * 60 * 60,
  weeks: 7 * 24 * 60 * 60,
  months: 30 * 24 * 60 * 60,
}

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
  if (profile.is_visible) return { label: 'Published', className: 'published' }
  if (profile.is_configured) return { label: 'Draft', className: 'draft' }
  return { label: 'Not configured', className: 'unconfigured' }
}

function ProfileEditor({ hostel, profile, onClose, onSave }) {
  const startingDuration = durationParts(
    profile.duration_seconds,
    profile.is_configured ? null : profile.session_timeout,
  )
  const [form, setForm] = useState({
    displayName: profile.display_name || titleFromProfile(profile.mikrotik_profile),
    description: profile.description || '',
    amount: profile.amount ?? '',
    currency: profile.currency || 'GHS',
    durationValue: startingDuration.value,
    durationUnit: startingDuration.unit,
    dataLimitGb: profile.data_limit_bytes ? profile.data_limit_bytes / 1024 ** 3 : '',
    deviceLimit: profile.device_limit || profile.shared_users || 1,
    downloadSpeed: profile.download_speed || '',
    isPromotional: profile.is_promotional || false,
    isVisible: profile.is_registration_profile ? false : profile.is_visible,
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

          <footer className="profile-drawer-actions">
            <button className="drawer-cancel" disabled={saving} type="button" onClick={onClose}>Cancel</button>
            <button className="drawer-save" disabled={saving} type="submit">{saving ? 'Saving changes...' : 'Save changes'}</button>
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

function HostelTable({ hostels, canEdit, loading, onAdd, onEdit, onProfiles }) {
  return (
    <section className="hostels-card">
      <header className="hostels-card-heading">
        <div><h2>All hostels</h2><p>View and manage the router locations stored in the database.</p></div>
        {canEdit && <button type="button" onClick={onAdd}>+ Add hostel</button>}
      </header>
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
              <td><div className="hostel-row-actions"><button type="button" onClick={() => onEdit(hostel.router_id)}>{canEdit ? 'Edit' : 'View'}</button><button type="button" onClick={() => onProfiles(hostel.router_id)}>Plans</button></div></td>
            </tr>)}</tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function ProfileTable({ profiles, query, filter, onEdit }) {
  const visibleProfiles = profiles.filter((profile) => {
    const matchesQuery = `${profile.display_name || ''} ${profile.mikrotik_profile}`
      .toLowerCase().includes(query.toLowerCase())
    const matchesFilter = filter === 'all'
      || (filter === 'published' && profile.is_visible)
      || (filter === 'drafts' && !profile.is_visible)
    return matchesQuery && matchesFilter
  })

  if (!visibleProfiles.length) {
    return <div className="profiles-empty"><Icon name="search" /><h3>No matching profiles</h3><p>Try another search or filter.</p></div>
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
                <td><button className="profile-edit-button" disabled={!profile.available_on_router} type="button" onClick={() => onEdit(profile)}>{profile.is_configured ? 'Edit' : 'Configure'}<Icon name="chevron" /></button></td>
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
  const [signingOut, setSigningOut] = useState(false)

  const selectedHostel = hostels.find((hostel) => hostel.router_id === selectedId) || null
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
    listHostelProfiles(selectedId)
      .then((items) => {
        if (!active) return
        setProfiles(items)
        setHostels((current) => current.map((hostel) => (
          hostel.router_id === selectedId
            ? { ...hostel, status: 'online', last_seen_at: new Date().toISOString() }
            : hostel
        )))
      })
      .catch((error) => {
        if (!active) return
        setHostels((current) => current.map((hostel) => (
          hostel.router_id === selectedId ? { ...hostel, status: 'offline' } : hostel
        )))
        handleError(error, 'The router could not be reached. Check its connection and try again.')
      })
      .finally(() => { if (active) setLoadingProfiles(false) })
    return () => { active = false }
  }, [selectedId, view])

  async function refreshProfiles() {
    if (!selectedId) return
    setLoadingProfiles(true)
    setPageError('')
    try {
      setProfiles(await listHostelProfiles(selectedId))
      setToast('Profiles refreshed from the router.')
      window.setTimeout(() => setToast(''), 3000)
    } catch (error) {
      setHostels((current) => current.map((hostel) => (
        hostel.router_id === selectedId ? { ...hostel, status: 'offline' } : hostel
      )))
      handleError(error, 'The router could not be reached. Check its connection and try again.')
    } finally {
      setLoadingProfiles(false)
    }
  }

  async function saveProfile(payload) {
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
          <button className="coming-soon" disabled type="button"><Icon name="settings" />Settings<small>Soon</small></button>
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
          <div className="dashboard-mobile-tabs"><button className={view === 'hostels' ? 'active' : ''} type="button" onClick={() => setView('hostels')}>Hostels</button><button className={view === 'profiles' ? 'active' : ''} type="button" onClick={() => setView('profiles')}>Profiles</button></div>
          {view === 'hostels' ? <>
            <header className="dashboard-page-heading">
              <div><p className="dashboard-kicker">Network management</p><h1>Hostels</h1><p>Add and manage the hostel routers stored in the database.</p></div>
            </header>
            <HostelTable canEdit={admin.role !== 'viewer'} hostels={hostels} loading={loadingHostels} onAdd={() => setViewingHostel('new')} onEdit={openHostel} onProfiles={openProfiles} />
          </> : <>
          <header className="dashboard-page-heading">
            <div><p className="dashboard-kicker">Network catalogue</p><h1>Hostel profiles</h1><p>Turn MikroTik profiles into clear, customer-ready WiFi plans.</p></div>
            <div className="hostel-selector">
              <label htmlFor="hostel-select">Selected hostel</label>
              <div><Icon name="building" /><select disabled={loadingHostels || !hostels.length} id="hostel-select" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>{hostels.map((hostel) => <option key={hostel.router_id} value={hostel.router_id}>{hostel.name}</option>)}</select></div>
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
                <button disabled={!selectedHostel} type="button" onClick={() => setViewingHostel('details')}><Icon name="settings" />View details</button>
                <button disabled={loadingProfiles || !selectedHostel?.is_active} type="button" onClick={refreshProfiles}><Icon name="refresh" />{loadingProfiles ? 'Syncing...' : 'Sync from router'}</button>
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
              <ProfileTable filter={filter} profiles={profiles} query={query} onEdit={setEditingProfile} />
            )}
          </section>
          </>}
        </div>
      </main>

      {editingProfile && selectedHostel && <ProfileEditor hostel={selectedHostel} profile={editingProfile} onClose={() => setEditingProfile(null)} onSave={saveProfile} />}
      {viewingHostel === 'details' && selectedHostel && <HostelEditor canEdit={admin.role !== 'viewer'} hostel={selectedHostel} onClose={() => setViewingHostel(false)} onSave={saveHostel} />}
      {viewingHostel === 'new' && <HostelEditor canEdit hostel={null} onClose={() => setViewingHostel(false)} onSave={addHostel} />}
      {toast && <div className="dashboard-toast" role="status"><Icon name="check" />{toast}</div>}
    </div>
  )
}
