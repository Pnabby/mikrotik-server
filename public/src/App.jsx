import DeviceList from './components/DeviceList'
import Header from './components/Header'
import LoadingOverlay from './components/LoadingOverlay'
import LogoutModal from './components/LogoutModal'
import LookupModal from './components/LookupModal'
import Overview, { AccountPanel } from './components/Overview'
import { DevicesIcon, RefreshIcon, VoucherIcon } from './components/Icons'
import { useHotspotStatus } from './hooks/useHotspotStatus'
import LoginPage from './pages/LoginPage'
import SignupPage from './pages/SignupPage'
import { formatDeviceCount, formatLimit, formatTime, normalizeText } from './utils/formatters'

function buildView({ active, errorMessage, lastUpdated, payload, phase }) {
  const hasData = Boolean(payload) && phase !== 'error' && phase !== 'idle'
  const loaded = phase === 'loaded' && payload
  const disabled = loaded?.disabled === true

  let lockedUsername = active.username || 'Waiting for hotspot session'
  let lockedNote = 'Open this page from your hotspot status page, or search with voucher credentials.'
  let statusDot = 'idle'
  let statusText = 'Waiting for a hotspot session or voucher search'
  if (phase === 'bootstrapping') {
    statusDot = 'loading'
    statusText = 'Loading hotspot session'
  } else if (phase === 'loading') {
    lockedNote = active.isLookupResult
      ? 'Verifying the voucher credentials and loading its details.'
      : 'Loading the locked voucher details for this hotspot user.'
    statusDot = 'loading'
    statusText = 'Loading...'
  } else if (phase === 'loaded') {
    lockedUsername = payload.username
    lockedNote = active.isLookupResult
      ? `Voucher details were verified for the ${payload.router_name} hostel.`
      : `Voucher details are locked to your current hotspot session at ${payload.router_name}.`
    statusDot = disabled ? 'warning' : 'active'
    statusText = disabled
      ? 'Voucher disabled — it may be expired or exhausted'
      : `${payload.username} loaded`
  } else if (phase === 'error') {
    lockedNote = active.isLookupResult
      ? 'The supplied voucher credentials could not be verified.'
      : 'The voucher session is locked, but the details could not be loaded right now.'
    statusDot = 'error'
    statusText = 'Load failed'
  }

  return {
    accountStatus: loaded ? (disabled ? 'Expired or exhausted' : 'Active') : '--',
    dataLeft: hasData ? payload.total_data_left || 'Unlimited' : '--',
    dataLimit: loaded ? formatLimit(payload.data_limit_bytes) : '--',
    dataUsed: hasData ? payload.total_data_used || '0 B' : '--',
    detailUsername: loaded ? payload.username : active.username || '--',
    deviceCount: hasData ? String(payload.connected_devices_count || 0) : '--',
    devicesBadge: loaded ? formatDeviceCount(payload.connected_devices_count) : phase === 'loading' ? '...' : '0 devices',
    errorMessage,
    expiryDate: loaded ? normalizeText(payload.expiry_date) || 'N/A' : '--',
    lastUpdated: loaded && lastUpdated ? formatTime(lastUpdated) : phase === 'error' ? 'Failed' : 'No data',
    lockedNote,
    lockedUsername,
    loggedInDate: loaded ? normalizeText(payload.logged_in_date) || 'N/A' : '--',
    overviewBadge: loaded ? (disabled ? 'Used' : 'Active') : phase === 'loading' ? '...' : 'Idle',
    overviewBadgeClass: loaded ? (disabled ? 'panel-badge warning' : 'panel-badge active') : 'panel-badge',
    profile: hasData ? normalizeText(payload.profile) || 'None' : '--',
    routerName: loaded ? payload.router_name : active.routerName || active.routerId || '--',
    statusDot,
    statusText,
  }
}

function StatusPage() {
  const hotspot = useHotspotStatus()
  const view = buildView(hotspot)
  const busy = hotspot.phase === 'loading' || hotspot.phase === 'bootstrapping'
  const devices = hotspot.payload?.connected_devices || []

  return (
    <>
      <div className="container">
        <Header phase={hotspot.phase} username={hotspot.active.username} />

        <div className="voucher-lookup-card">
          <div className="voucher-lookup-icon" aria-hidden="true"><VoucherIcon /></div>
          <div className="voucher-lookup-copy">
            <div className="voucher-lookup-title">Check a different voucher</div>
            <div className="voucher-lookup-text">View its usage, plan, expiry date, and connected devices.</div>
          </div>
          <button className="btn btn-primary voucher-lookup-button" type="button" onClick={hotspot.openLookup}>Check voucher</button>
        </div>

        <div className="session-section">
          <div className="session-bar">
            <div className="session-copy">
              <div className="session-title">Voucher Details</div>
              <div className={`session-username${hotspot.active.username ? '' : ' empty'}`}>{view.lockedUsername}</div>
              <div className="session-note">{view.lockedNote}</div>
            </div>
            <button className="btn btn-outline icon-btn" type="button" onClick={hotspot.refresh} disabled={!hotspot.active.username || busy}><RefreshIcon />Refresh</button>
          </div>
        </div>

        <div className="status-bar">
          <span className={`status-dot ${view.statusDot}`} />
          <span>{view.statusText}</span>
        </div>

        <Overview view={view} />

        <div className="panels">
          <AccountPanel view={view} />
          <div className="panel">
            <div className="panel-header">
              <h2 className="panel-title"><DevicesIcon />Devices</h2>
              <span className="panel-badge">{view.devicesBadge}</span>
            </div>
            <div className="devices-container">
              <DeviceList phase={hotspot.phase} devices={devices} session={hotspot.session} onLogout={hotspot.requestLogout} errorMessage={hotspot.errorMessage} />
            </div>
          </div>
        </div>
        <div className="page-footer">Powered by FlintWiFi</div>
      </div>

      {busy && <LoadingOverlay lookup={hotspot.active.isLookupResult} longLoading={hotspot.longLoading} />}
      {hotspot.lookupOpen && (
        <LookupModal
          activeRouterId={hotspot.active.routerId}
          error={hotspot.lookupError}
          loading={hotspot.phase === 'loading'}
          onClose={hotspot.closeLookup}
          onLookup={hotspot.lookup}
          routers={hotspot.session?.routers || []}
        />
      )}
      {hotspot.logoutTarget && (
        <LogoutModal
          device={hotspot.logoutTarget}
          error={hotspot.logoutError}
          loading={hotspot.logoutLoading}
          username={hotspot.active.username}
          onClose={hotspot.closeLogout}
          onConfirm={hotspot.confirmLogout}
        />
      )}
    </>
  )
}

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, '')
  if (path === '/status' || path.startsWith('/status/')) return <StatusPage />
  if (path === '/signup') return <SignupPage />
  return <LoginPage />
}
