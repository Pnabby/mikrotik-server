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
  claimFreePlan,
  disconnectAccountDevice,
  getAccount,
  getAccountHotspotStatus,
  initializePlanPurchase,
  retryFreePlanClaim,
  verifyPlanPurchase,
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

function formatDateTime(value, fallback = '--') {
  if (!value) return fallback
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('en-GH', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}

function timestampHasPassed(value) {
  if (!value) return false
  const normalizedValue = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)
    ? `${value.replace(' ', 'T')}Z`
    : value
  const timestamp = new Date(normalizedValue).getTime()
  return Number.isFinite(timestamp) && timestamp <= Date.now()
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

function friendlyPaymentStatus(status, amount = null) {
  if (status === 'success' && Number(amount) === 0) return 'Claimed'
  const labels = { failed: 'Failed', pending: 'Pending', success: 'Paid' }
  return labels[status] || 'Unavailable'
}

function noticeForPaymentResult(result) {
  if (result.payment_status === 'failed') return 'failed'
  if (result.payment_status === 'success' && result.activation_status === 'success') return 'active'
  if (result.payment_status === 'success' && result.activation_status === 'superseded') return 'promo_already_used'
  return result.payment_status === 'success' ? 'activation_pending' : 'pending'
}

const AUTOMATIC_ACTIVATION_STATUSES = new Set([
  'not_started',
  'processing',
  'provisioning',
  'retry_required',
  'reconciliation_required',
])

const PAYMENT_NOTICE_COPY = {
  active: {
    title: 'Your plan is active.',
    detail: 'You can now open the WiFi login page and connect.',
  },
  activation_pending: {
    title: 'Your plan is being activated.',
    detail: 'Your transaction is safe. We are automatically retrying the router; you can also retry it now.',
  },
  pending: {
    title: 'Your payment is still being confirmed.',
    detail: 'Check again shortly to see the latest status.',
  },
  promo_already_used: {
    title: 'This promotional plan was already claimed.',
    detail: 'Only the first successful claim or purchase can activate this one-time offer. Please contact support if you need help.',
  },
  failed: {
    title: 'The payment was not completed.',
    detail: 'No plan was activated. You can select a plan and try again.',
  },
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

function PlanCard({ plan, purchasingPlanId, onPurchase }) {
  const isFreePromotion = plan.is_promotional && Number(plan.amount) === 0
  return (
    <article className={`plan-card${plan.is_promotional ? ' plan-card-promo' : ''}`}>
      <div>
        <div className="plan-card-labels">
          <span className="plan-duration">{formatDuration(plan.duration_seconds)}</span>
          {plan.is_promotional && <span className="plan-promo-label">Promo &middot; once per customer</span>}
        </div>
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
        <button type="button" disabled={!plan.purchase_available || Boolean(purchasingPlanId)} onClick={() => onPurchase(plan)}>
          {purchasingPlanId === plan.id ? (isFreePromotion ? 'Activating...' : 'Opening checkout...') : plan.promo_claimed ? 'Promo already claimed' : plan.purchase_available ? (isFreePromotion ? 'Claim free plan' : 'Purchase plan') : 'Payments unavailable'}
        </button>
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
  const [showAllPurchases, setShowAllPurchases] = useState(false)
  const [activeSection, setActiveSection] = useState('overview')
  const [purchasingPlanId, setPurchasingPlanId] = useState('')
  const [purchaseError, setPurchaseError] = useState('')
  const [purchaseTarget, setPurchaseTarget] = useState(null)
  const [paymentNotice, setPaymentNotice] = useState(() => {
    const value = new URLSearchParams(window.location.search).get('payment')
    return ['active', 'activation_pending', 'pending', 'failed', 'promo_already_used'].includes(value) ? value : ''
  })
  const [paymentReference, setPaymentReference] = useState(() => new URLSearchParams(window.location.search).get('reference') || '')
  const [checkingPayment, setCheckingPayment] = useState(false)
  const recoverablePurchase = account?.purchases?.find((purchase) => (
    purchase.status === 'success'
      && AUTOMATIC_ACTIVATION_STATUSES.has(purchase.activation_status)
  ))
  const activationReference = paymentReference || recoverablePurchase?.reference || ''
  const visiblePaymentNotice = paymentNotice || (recoverablePurchase ? 'activation_pending' : '')

  useEffect(() => {
    document.title = 'Overview | Vlad WiFi'
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

  useEffect(() => {
    if (!activationReference || !['activation_pending', 'pending'].includes(visiblePaymentNotice)) return undefined

    let active = true
    let timerId = null
    let attempts = 0

    async function pollPayment() {
      if (!active) return
      attempts += 1
      setCheckingPayment(true)
      try {
        const result = activationReference.startsWith('FREE-')
          ? await retryFreePlanClaim(activationReference)
          : await verifyPlanPurchase(activationReference)
        if (!active) return
        const nextNotice = noticeForPaymentResult(result)
        if (nextNotice === 'active') {
          window.location.replace('/account?payment=active')
          return
        }
        setPaymentNotice(nextNotice)
        if (nextNotice !== 'failed' && attempts < 20) {
          timerId = window.setTimeout(pollPayment, 3000)
        }
      } catch (error) {
        if (!active) return
        if (error instanceof AccountApiError && error.status === 401) {
          window.location.replace('/')
          return
        }
        if (attempts < 20) timerId = window.setTimeout(pollPayment, 3000)
      } finally {
        if (active) setCheckingPayment(false)
      }
    }

    timerId = window.setTimeout(pollPayment, 1500)
    return () => {
      active = false
      if (timerId !== null) window.clearTimeout(timerId)
    }
  }, [activationReference, visiblePaymentNotice])

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

  async function purchasePlan(plan) {
    if (!plan.purchase_available || purchasingPlanId) return
    setPurchasingPlanId(plan.id)
    setPurchaseError('')
    try {
      if (plan.is_promotional && Number(plan.amount) === 0) {
        const result = await claimFreePlan(plan.id)
        const nextNotice = noticeForPaymentResult(result)
        if (nextNotice === 'active') {
          window.location.replace('/account?payment=active')
          return
        }
        setPaymentReference(result.reference)
        setPaymentNotice(nextNotice)
        setPurchaseTarget(null)
        setPurchasingPlanId('')
        return
      }
      const checkout = await initializePlanPurchase(plan.id)
      window.location.assign(checkout.authorization_url)
    } catch (error) {
      if (error instanceof AccountApiError && error.status === 401) {
        window.location.replace('/')
        return
      }
      setPurchaseError(
        error instanceof AccountApiError && error.status === 409
          ? error.detail || 'This promotional plan has already been claimed.'
          : error instanceof AccountApiError && error.status === 503
          ? 'The router is currently unreachable. Please contact support.'
          : 'Checkout could not be started. Please try again in a moment.',
      )
      setPurchaseTarget(null)
      setPurchasingPlanId('')
    }
  }

  function requestPlanPurchase(plan) {
    setPurchaseError('')
    if (account?.current_plan && !isCurrentPlanExhausted) {
      setPurchaseTarget(plan)
      return
    }
    purchasePlan(plan)
  }

  async function checkPayment(reference = activationReference) {
    if (!reference || checkingPayment) return
    setCheckingPayment(true)
    try {
      const result = reference.startsWith('FREE-')
        ? await retryFreePlanClaim(reference)
        : await verifyPlanPurchase(reference)
      const nextNotice = noticeForPaymentResult(result)
      if (nextNotice === 'active') {
        window.location.replace('/account?payment=active')
        return
      }
      setPaymentNotice(nextNotice)
    } catch (error) {
      if (error instanceof AccountApiError && error.status === 401) {
        window.location.replace('/')
        return
      }
      setPaymentNotice('pending')
    } finally {
      setCheckingPayment(false)
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
  const hasCurrentPlan = Boolean(currentPlan)
  const dataAllowanceExhausted = hasCurrentPlan
    && networkStatus?.total_data_left_bytes !== null
    && networkStatus?.total_data_left_bytes !== undefined
    && Number(networkStatus.total_data_left_bytes) <= 0
  const planExpiryDate = networkStatus?.expiry_date || currentPlan?.expires_at || null
  const isCurrentPlanExhausted = dataAllowanceExhausted || timestampHasPassed(planExpiryDate)
  const devices = networkStatus?.connected_devices || []
  const statusUnavailable = networkPhase === 'error'
  const planName = currentPlan?.name || ''
  // Login and expiry timing come from RouterOS, never from the payment timestamp.
  const loginDate = networkStatus?.logged_in_date || null
  const expiryDate = planExpiryDate
  const loginDateLabel = formatDate(loginDate, 'Awaiting first login')
  const expiryDateLabel = expiryDate
    ? formatDate(expiryDate)
    : currentPlan?.duration_seconds === null || currentPlan?.duration_seconds === undefined
      ? 'Non expiry'
      : loginDate
        ? 'Managed by WiFi portal'
        : 'Starts after first login'
  const availablePlans = account.available_plans || []
  const hasPlanGroups = availablePlans.some((plan) => plan.group_id)
  const visiblePlans = hasPlanGroups || showAllPlans ? availablePlans : availablePlans.slice(0, 3)
  const planSections = hasPlanGroups
    ? Array.from(visiblePlans.reduce((sections, plan) => {
      const key = plan.group_id || '__ungrouped__'
      if (!sections.has(key)) sections.set(key, {
        id: key,
        name: plan.group_name || 'Other plans',
        description: plan.group_description || '',
        displayOrder: plan.group_display_order ?? Number.MAX_SAFE_INTEGER,
        sortByPrice: plan.group_sort_by_price,
        plans: [],
      })
      sections.get(key).plans.push(plan)
      return sections
    }, new Map()).values())
      .map((section) => ({
        ...section,
        plans: [...section.plans].sort((left, right) => (
          Number(right.is_promotional) - Number(left.is_promotional)
          || (section.sortByPrice
            ? Number(left.amount) - Number(right.amount)
            : left.name.localeCompare(right.name))
        )),
      }))
      .sort((left, right) => (
        Number(right.plans.some((plan) => plan.is_promotional))
        - Number(left.plans.some((plan) => plan.is_promotional))
        || left.displayOrder - right.displayOrder
        || left.name.localeCompare(right.name)
      ))
    : [{ id: '__all__', name: '', description: '', plans: visiblePlans }]
  const previousPlans = account.previous_plans || []
  const purchases = account.purchases || []
  const visiblePurchases = showAllPurchases ? purchases : purchases.slice(0, 5)
  const paymentNoticeCopy = PAYMENT_NOTICE_COPY[visiblePaymentNotice]

  return (
    <main className="account-page">
      <AccountHeader account={account} activeSection={activeSection} />
      <div className="account-shell">
        {visiblePaymentNotice && (
          <div className={`payment-notice payment-notice-${visiblePaymentNotice}`} role="status">
            <div>
              <strong>{paymentNoticeCopy.title}</strong>
              <span>{paymentNoticeCopy.detail}</span>
            </div>
            {activationReference && ['activation_pending', 'pending'].includes(visiblePaymentNotice) && (
              <button type="button" disabled={checkingPayment} onClick={() => checkPayment()}>{checkingPayment ? 'Retrying...' : 'Retry activation'}</button>
            )}
          </div>
        )}
        <section className="dashboard-heading" id="overview">
          <div>
            <span className="account-eyebrow">Overview</span>
            <h1>Good to see you, {account.username}</h1>
            <p>Track your WiFi access, devices, plans, and purchases.</p>
          </div>
          {hasCurrentPlan && (
            <div className={`network-state ${isCurrentPlanExhausted ? 'network-exhausted' : 'network-active'}`}>
              <span><DotIcon /></span>
              <div><small>WiFi access</small><strong>{isCurrentPlanExhausted ? 'Exhausted' : 'Active plan'}</strong></div>
            </div>
          )}
        </section>

        {hasCurrentPlan && (
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

        {hasCurrentPlan && (
          <section className="account-section plan-breakdown-section" aria-labelledby="plan-breakdown-title">
            <div className="account-section-heading">
              <div>
                <span className="account-eyebrow">Your plan</span>
                <h2 id="plan-breakdown-title">Plan breakdown</h2>
                <p>Your current WiFi plan and access details.</p>
              </div>
              <span className={`plan-breakdown-status${isCurrentPlanExhausted ? ' exhausted' : ''}`}><DotIcon />{isCurrentPlanExhausted ? 'Exhausted' : 'Active'}</span>
            </div>
            <dl className="plan-breakdown-list">
              <div><dt>Plan</dt><dd>{planName}</dd></div>
              <div><dt>Login date</dt><dd>{loginDateLabel}</dd></div>
              <div><dt>Expiry date</dt><dd>{expiryDateLabel}</dd></div>
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

        {hasCurrentPlan && (
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
            <div className="plan-heading-actions">
              {!hasPlanGroups && availablePlans.length > 3 && <button type="button" aria-expanded={showAllPlans} onClick={() => setShowAllPlans((current) => !current)}>{showAllPlans ? 'Show featured plans' : `View all ${availablePlans.length} plans`}</button>}
              <VoucherIcon />
            </div>
          </div>
          <div className="plan-speed-notice" role="note"><DataUsedIcon /><p><strong>Understanding your plan speed</strong><span>The speed shown is the maximum a plan can reach. Actual speed cannot be guaranteed, especially during peak hours, and your distance from the WiFi router or access point can also affect it.</span></p></div>
          {availablePlans.length ? (
            <>
              {purchaseError && <div className="plan-purchase-error" role="alert">{purchaseError}</div>}
              <div className={hasPlanGroups ? 'plan-group-sections' : ''}>
                {planSections.map((section) => (
                  <section className={hasPlanGroups ? 'customer-plan-group' : ''} key={section.id}>
                    {hasPlanGroups && <header><span>Plan collection</span><h3>{section.name}</h3>{section.description && <p>{section.description}</p>}</header>}
                    <div className="plans-grid">
                      {section.plans.map((plan) => <PlanCard key={plan.id} plan={plan} purchasingPlanId={purchasingPlanId} onPurchase={requestPlanPurchase} />)}
                    </div>
                  </section>
                ))}
              </div>
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
                    <div><dt>Purchase date</dt><dd>{formatDateTime(plan.purchased_at)}</dd></div>
                  </dl>
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
          {purchases.length ? (
            <>
              <div className="purchase-table-wrap">
                <table className="purchase-table">
                  <thead><tr><th>Plan</th><th>Date</th><th>Amount</th><th>Status</th><th>Reference</th></tr></thead>
                  <tbody>
                    {visiblePurchases.map((purchase) => (
                      <tr key={purchase.reference}>
                        <td><strong>{purchase.plan_name}</strong></td>
                        <td>{formatDateTime(purchase.paid_at || purchase.purchased_at)}</td>
                        <td>{formatMoney(purchase.amount, purchase.currency)}</td>
                        <td>
                          <span className={`purchase-status purchase-${purchase.status}`}>{friendlyPaymentStatus(purchase.status, purchase.amount)}</span>
                          {purchase.status === 'success' && purchase.activation_status && !['success', 'superseded'].includes(purchase.activation_status) && (
                            <button
                              className="purchase-activation-retry"
                              type="button"
                              disabled={checkingPayment}
                              onClick={() => checkPayment(purchase.reference)}
                            >
                              {checkingPayment && activationReference === purchase.reference ? 'Retrying...' : 'Retry activation'}
                            </button>
                          )}
                        </td>
                        <td><code>{purchase.reference}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {purchases.length > 5 && (
                <div className="plan-list-actions">
                  <button type="button" aria-expanded={showAllPurchases} onClick={() => setShowAllPurchases((current) => !current)}>
                    {showAllPurchases ? 'Show fewer purchases' : `View more purchases (${purchases.length - 5})`}
                  </button>
                </div>
              )}
            </>
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

      {purchaseTarget && (
        <div className="portal-modal-backdrop" role="presentation" onMouseDown={() => !purchasingPlanId && setPurchaseTarget(null)}>
          <section className="portal-modal" role="dialog" aria-modal="true" aria-labelledby="replace-plan-title" onMouseDown={(event) => event.stopPropagation()}>
            <span className="portal-modal-icon plan-replace-icon"><WarningIcon /></span>
            <h2 id="replace-plan-title">Replace your active plan?</h2>
            <p>
              You currently have <strong>{currentPlan.name}</strong>. {purchaseTarget.is_promotional && Number(purchaseTarget.amount) === 0 ? 'Claiming' : 'Purchasing'} <strong>{purchaseTarget.name}</strong> will immediately replace it. Any remaining time or data on your current plan will not carry over. All connected devices will be logged out and every device must sign in through the WiFi portal again.
            </p>
            <div className="portal-modal-actions">
              <button type="button" onClick={() => setPurchaseTarget(null)} disabled={Boolean(purchasingPlanId)}>Keep current plan</button>
              <button
                className="confirm"
                type="button"
                disabled={Boolean(purchasingPlanId)}
                onClick={() => purchasePlan(purchaseTarget)}
              >
                {purchasingPlanId ? (purchaseTarget.is_promotional && Number(purchaseTarget.amount) === 0 ? 'Activating...' : 'Opening checkout...') : purchaseTarget.is_promotional && Number(purchaseTarget.amount) === 0 ? 'Claim and replace' : 'Replace and continue'}
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  )
}
