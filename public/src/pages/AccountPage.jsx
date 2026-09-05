import { useEffect, useState } from 'react'

import AccountHeader from '../components/AccountHeader'
import {
  CheckIcon,
  DataLeftIcon,
  DataUsedIcon,
  DevicesIcon,
  DeviceTypeIcon,
  DotIcon,
  PlanIcon,
  ShieldIcon,
  VoucherIcon,
  WarningIcon,
} from '../components/Icons'
import {
  AccountApiError,
  disconnectAccountDevice,
  getAccount,
  getAccountHotspotStatus,
} from '../services/accountApi'

function formatMoney(amount, currency) {
  const numericAmount = Number(amount)
  if (!Number.isFinite(numericAmount)) return '--'
  try {
    return new Intl.NumberFormat('en-GH', {
      style: 'currency',
      currency: currency || 'GHS',
      minimumFractionDigits: 2,
    }).format(numericAmount)
  } catch {
    return `${currency || 'GHS'} ${numericAmount.toFixed(2)}`
  }
}

function formatDate(value, fallback = '--') {
  if (!value) return fallback
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('en-GH', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date)
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return 'Non expiry'
  const hours = Math.round(Number(seconds || 0) / 3600)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'}`
  const days = Math.round(hours / 24)
  return `${days} day${days === 1 ? '' : 's'}`
}

function formatData(bytes) {
  if (bytes === null || bytes === undefined) return 'Unlimited data'
  const gigabytes = Number(bytes) / (1024 ** 3)
  return `${gigabytes >= 1 ? gigabytes.toFixed(gigabytes % 1 ? 1 : 0) : '< 1'} GB data`
}

function formatBytes(bytes) {
  const value = Number(bytes || 0)
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`
  return `${(value / 1024 ** 3).toFixed(1)} GB`
}

function friendlyPaymentStatus(status) {
  const labels = { failed: 'Failed', pending: 'Pending', success: 'Paid' }
  return labels[status] || 'Unavailable'
}

function friendlyPlanStatus(status) {
  const labels = { cancelled: 'Cancelled', expired: 'Expired', superseded: 'Replaced' }
  return labels[status] || 'Ended'
}

function DeviceCard({ device, onDisconnect }) {
  return (
    <article className="portal-device-card">
      <div className="portal-device-icon"><DeviceTypeIcon type={device.device_type} /></div>
      <div className="portal-device-main">
        <div className="portal-device-heading">
          <div>
            <h3>{device.device_name || 'Unknown device'}</h3>
            <span><DotIcon /> Connected</span>
          </div>
          <button type="button" onClick={() => onDisconnect(device)}>Disconnect</button>
        </div>
        <dl className="portal-device-details">
          <div><dt>Device type</dt><dd>{device.device_type || 'Unknown'}</dd></div>
          <div><dt>IP address</dt><dd>{device.ip_address || 'N/A'}</dd></div>
          <div><dt>MAC address</dt><dd>{device.mac_address || 'N/A'}</dd></div>
          <div><dt>Uptime</dt><dd>{device.uptime || 'N/A'}</dd></div>
          <div><dt>Usage</dt><dd>{formatBytes(device.bytes_total)}</dd></div>
        </dl>
      </div>
    </article>
  )
}

export default function AccountPage() {
  const [account, setAccount] = useState(null)
  const [accountPhase, setAccountPhase] = useState('loading')
  const [networkStatus, setNetworkStatus] = useState(null)
  const [networkPhase, setNetworkPhase] = useState('loading')
  const [disconnectTarget, setDisconnectTarget] = useState(null)
  const [disconnecting, setDisconnecting] = useState(false)
  const [disconnectError, setDisconnectError] = useState('')
  const [showAllPlans, setShowAllPlans] = useState(false)
  const [activeSection, setActiveSection] = useState('overview')

  useEffect(() => {
    document.title = 'Overview | FLINT WiFi'
    let active = true

    async function load() {
      try {
        const result = await getAccount()
        if (!active) return
        setAccount(result)
        setAccountPhase('ready')
        if (!result.current_plan) {
          setNetworkPhase('ready')
          return
        }
      } catch (error) {
        if (!active) return
        if (error instanceof AccountApiError && error.status === 401) {
          window.location.replace('/')
          return
        }
        setAccountPhase('error')
        return
      }

      try {
        const result = await getAccountHotspotStatus()
        if (!active) return
        setNetworkStatus(result)
        setNetworkPhase('ready')
      } catch (error) {
        if (!active) return
        if (error instanceof AccountApiError && error.status === 401) {
          window.location.replace('/')
          return
        }
        setNetworkPhase('error')
      }
    }

    load()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (accountPhase !== 'ready') return undefined
    const sectionIds = ['overview', 'plans', 'purchases']
    let frameId = null

    function updateActiveSection() {
      frameId = null
      const marker = window.scrollY + Math.min(180, window.innerHeight * 0.3)
      let nextSection = 'overview'
      for (const sectionId of sectionIds) {
        const section = document.getElementById(sectionId)
        if (section && section.offsetTop <= marker) nextSection = sectionId
      }
      const reachedPageEnd = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4
      if (reachedPageEnd) nextSection = 'purchases'
      setActiveSection((current) => current === nextSection ? current : nextSection)
    }

    function scheduleUpdate() {
      if (frameId === null) frameId = window.requestAnimationFrame(updateActiveSection)
    }

    const requestedSection = window.location.hash.slice(1)
    if (sectionIds.includes(requestedSection)) {
      document.getElementById(requestedSection)?.scrollIntoView()
    }
    scheduleUpdate()
    window.addEventListener('scroll', scheduleUpdate, { passive: true })
    window.addEventListener('resize', scheduleUpdate)
    window.addEventListener('hashchange', scheduleUpdate)
    return () => {
      window.removeEventListener('scroll', scheduleUpdate)
      window.removeEventListener('resize', scheduleUpdate)
      window.removeEventListener('hashchange', scheduleUpdate)
      if (frameId !== null) window.cancelAnimationFrame(frameId)
    }
  }, [accountPhase])

  async function refreshNetworkStatus() {
    if (networkPhase === 'loading') return
    setNetworkPhase('loading')
    try {
      const result = await getAccountHotspotStatus()
      setNetworkStatus(result)
      setNetworkPhase('ready')
    } catch (error) {
      if (error instanceof AccountApiError && error.status === 401) {
        window.location.replace('/')
        return
      }
      setNetworkPhase('error')
    }
  }

  async function disconnectDevice() {
    if (!disconnectTarget || disconnecting) return
    setDisconnecting(true)
    setDisconnectError('')
    try {
      await disconnectAccountDevice(disconnectTarget)
      setDisconnectTarget(null)
      await refreshNetworkStatus()
    } catch (error) {
      if (error instanceof AccountApiError && error.status === 401) {
        window.location.replace('/')
        return
      }
      setDisconnectError('The device could not be disconnected. Please try again.')
    } finally {
      setDisconnecting(false)
    }
  }

  if (accountPhase === 'loading') {
    return (
      <main className="account-page account-state-page" aria-busy="true">
        <div className="account-loader" />
        <h1>Loading your account</h1>
      </main>
    )
  }
  if (accountPhase === 'error' || !account) {
    return (
      <main className="account-page account-state-page">
        <ShieldIcon />
        <h1>Your account could not be loaded</h1>
        <p>Please try again or contact help and support.</p>
        <button type="button" onClick={() => window.location.reload()}>Try again</button>
      </main>
    )
  }

  const currentPlan = account.current_plan
  const hasActivePlan = Boolean(currentPlan)
  const devices = networkStatus?.connected_devices || []
  const statusUnavailable = networkPhase === 'error'
  const planName = currentPlan?.name || ''
  const loginDate = networkStatus?.logged_in_date || currentPlan?.starts_at
  const expiryDate = networkStatus?.expiry_date || currentPlan?.expires_at
  const availablePlans = account.available_plans || []
  const visiblePlans = showAllPlans ? availablePlans : availablePlans.slice(0, 3)
  const previousPlans = account.previous_plans || []

  return (
    <main className="account-page">
      <AccountHeader account={account} activeSection={activeSection} />
      <div className="account-shell">
        <section className="dashboard-heading" id="overview">
          <div>
            <span className="account-eyebrow">Overview</span>
            <h1>Good to see you, {account.username}</h1>
            <p>Track your WiFi access, devices, plans, and purchases.</p>
          </div>
          {hasActivePlan && (
            <div className="network-state network-active">
              <span><DotIcon /></span>
              <div><small>WiFi access</small><strong>Active plan</strong></div>
            </div>
          )}
        </section>

        {hasActivePlan && (
          <section className="usage-grid" aria-label="WiFi usage summary">
            <article>
              <span><DataUsedIcon /></span>
              <div><small>Data used</small><strong>{statusUnavailable ? '--' : networkStatus?.total_data_used || '0 B'}</strong></div>
            </article>
            <article>
              <span><DataLeftIcon /></span>
              <div><small>Data remaining</small><strong>{statusUnavailable ? '--' : networkStatus?.total_data_left || '--'}</strong></div>
            </article>
            <article>
              <span><PlanIcon /></span>
              <div><small>Current plan</small><strong>{planName}</strong></div>
            </article>
            <article>
              <span><DevicesIcon /></span>
              <div><small>Connected devices</small><strong>{statusUnavailable ? '--' : networkStatus?.connected_devices_count ?? 0}</strong></div>
            </article>
          </section>
        )}

        {hasActivePlan && (
          <section className="account-section plan-breakdown-section" aria-labelledby="plan-breakdown-title">
            <div className="account-section-heading">
              <div>
                <span className="account-eyebrow">Your plan</span>
                <h2 id="plan-breakdown-title">Plan breakdown</h2>
                <p>Your current WiFi plan and access details.</p>
              </div>
              <span className="plan-breakdown-status"><DotIcon />Active</span>
            </div>
            <dl className="plan-breakdown-list">
              <div><dt>Plan</dt><dd>{planName}</dd></div>
              <div><dt>Login date</dt><dd>{formatDate(loginDate)}</dd></div>
              <div><dt>Expiry date</dt><dd>{formatDate(expiryDate, 'Non expiry')}</dd></div>
              <div><dt>Data limit</dt><dd>{formatData(networkStatus?.data_limit_bytes ?? currentPlan.data_limit_bytes)}</dd></div>
              <div><dt>Device allowance</dt><dd>{currentPlan.device_limit ? `${currentPlan.device_limit} device${currentPlan.device_limit === 1 ? '' : 's'}` : 'Unlimited devices'}</dd></div>
              <div><dt>Download speed</dt><dd>{currentPlan.download_speed || 'Not listed'}</dd></div>
            </dl>
            <div className="captive-portal-callout">
              <div><strong>Ready to connect?</strong><p>Open the WiFi login page to activate your plan on this device.</p></div>
              <a href="http://wifi.flint.net">Open WiFi login</a>
            </div>
          </section>
        )}

        {hasActivePlan && (
          <section className="account-section">
            <div className="account-section-heading">
              <div><span className="account-eyebrow">Connections</span><h2>Connected devices</h2><p>Review and disconnect devices currently using your account.</p></div>
              <DevicesIcon />
            </div>
            {networkPhase === 'loading' && !networkStatus ? (
              <div className="account-empty"><div className="inline-loader" /><p>Loading connected devices...</p></div>
            ) : statusUnavailable ? (
              <div className="account-empty"><WarningIcon /><h3>Devices could not be loaded</h3><p>Refresh your WiFi status and try again.</p></div>
            ) : devices.length ? (
              <div className="portal-device-list">
                {devices.map((device) => (
                  <DeviceCard
                    key={device.session_id || `${device.mac_address}-${device.ip_address}`}
                    device={device}
                    onDisconnect={(selected) => {
                      setDisconnectError('')
                      setDisconnectTarget(selected)
                    }}
                  />
                ))}
              </div>
            ) : (
              <div className="account-empty"><DevicesIcon /><h3>No connected devices</h3><p>Your active devices will appear here.</p></div>
            )}
          </section>
        )}

        <section className="account-section" id="plans">
          <div className="account-section-heading">
            <div><span className="account-eyebrow">Get connected</span><h2>Available plans</h2><p>Choose the plan that fits your needs.</p></div>
            <VoucherIcon />
          </div>
          {availablePlans.length ? (
            <>
              <div className="plans-grid">
                {visiblePlans.map((plan) => (
                  <article className="plan-card" key={plan.id}>
                    <div>
                      <span className="plan-duration">{formatDuration(plan.duration_seconds)}</span>
                      <h3>{plan.name}</h3>
                      <p>{plan.description || 'Reliable WiFi access for your stay.'}</p>
                    </div>
                    <ul>
                      <li><CheckIcon />{formatData(plan.data_limit_bytes)}</li>
                      {plan.download_speed && <li><DataUsedIcon />Up to {plan.download_speed} download</li>}
                      <li><DevicesIcon />{plan.device_limit ? `${plan.device_limit} device${plan.device_limit === 1 ? '' : 's'}` : 'Unlimited devices'}</li>
                    </ul>
                    <div className="plan-card-footer">
                      <strong>{formatMoney(plan.amount, plan.currency)}</strong>
                      <button type="button" disabled={!plan.purchase_available}>
                        {plan.purchase_available ? 'Purchase plan' : 'Payments unavailable'}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
              {availablePlans.length > 3 && (
                <div className="plan-list-actions">
                  <button type="button" aria-expanded={showAllPlans} onClick={() => setShowAllPlans((current) => !current)}>
                    {showAllPlans ? 'Show fewer plans' : `View all plans (${availablePlans.length})`}
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="account-empty"><PlanIcon /><h3>No plans are available yet</h3><p>Please contact help and support for assistance.</p></div>
          )}
        </section>

        <section className="account-section" id="previous-plans">
          <div className="account-section-heading">
            <div><span className="account-eyebrow">Plan history</span><h2>Previous plans</h2><p>Your five most recent subscriptions.</p></div>
            <PlanIcon />
          </div>
          {previousPlans.length ? (
            <div className="previous-plans-list">
              {previousPlans.map((plan) => (
                <article className="previous-plan" key={plan.id}>
                  <div className="previous-plan-name">
                    <span><PlanIcon /></span>
                    <div><h3>{plan.name}</h3><small>Previous subscription</small></div>
                  </div>
                  <dl>
                    <div><dt>Login date</dt><dd>{formatDate(plan.starts_at)}</dd></div>
                    <div><dt>Expiry date</dt><dd>{formatDate(plan.expires_at || plan.ended_at, 'Non expiry')}</dd></div>
                  </dl>
                  <span className={`previous-plan-status status-${plan.status}`}>{friendlyPlanStatus(plan.status)}</span>
                </article>
              ))}
            </div>
          ) : (
            <div className="account-empty"><PlanIcon /><h3>No previous plans</h3><p>Your completed subscriptions will appear here.</p></div>
          )}
        </section>

        <section className="account-section" id="purchases">
          <div className="account-section-heading">
            <div><span className="account-eyebrow">Billing</span><h2>Purchase history</h2><p>Your latest plan purchases and payment status.</p></div>
            <VoucherIcon />
          </div>
          {account.purchases.length ? (
            <div className="purchase-table-wrap">
              <table className="purchase-table">
                <thead><tr><th>Plan</th><th>Date</th><th>Amount</th><th>Status</th><th>Reference</th></tr></thead>
                <tbody>
                  {account.purchases.map((purchase) => (
                    <tr key={purchase.reference}>
                      <td><strong>{purchase.plan_name}</strong></td>
                      <td>{formatDate(purchase.paid_at || purchase.purchased_at)}</td>
                      <td>{formatMoney(purchase.amount, purchase.currency)}</td>
                      <td><span className={`purchase-status purchase-${purchase.status}`}>{friendlyPaymentStatus(purchase.status)}</span></td>
                      <td><code>{purchase.reference}</code></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="account-empty"><VoucherIcon /><h3>No purchases yet</h3><p>Your plan purchases will appear here.</p></div>
          )}
        </section>

        <footer className="account-footer"><ShieldIcon /><span>Need help with your account or a purchase? Contact help and support.</span></footer>
      </div>

      {disconnectTarget && (
        <div className="portal-modal-backdrop" role="presentation" onMouseDown={() => !disconnecting && setDisconnectTarget(null)}>
          <section className="portal-modal" role="dialog" aria-modal="true" aria-labelledby="disconnect-title" onMouseDown={(event) => event.stopPropagation()}>
            <span className="portal-modal-icon"><DevicesIcon /></span>
            <h2 id="disconnect-title">Disconnect this device?</h2>
            <p>{disconnectTarget.device_name || 'This device'} will lose access immediately.</p>
            {disconnectError && <div className="portal-modal-error" role="alert">{disconnectError}</div>}
            <div className="portal-modal-actions">
              <button type="button" onClick={() => setDisconnectTarget(null)} disabled={disconnecting}>Cancel</button>
              <button className="danger" type="button" onClick={disconnectDevice} disabled={disconnecting}>{disconnecting ? 'Disconnecting...' : 'Disconnect'}</button>
            </div>
          </section>
        </div>
      )}
    </main>
  )
}
