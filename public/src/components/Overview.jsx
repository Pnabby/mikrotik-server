import { AccountIcon, DataLeftIcon, DataUsedIcon, DevicesIcon, PlanIcon } from './Icons'

function StatCard({ icon, label, value, accent = false }) {
  return (
    <div className="stat-card">
      <div className="stat-icon" aria-hidden="true">{icon}</div>
      <div className="stat-label">{label}</div>
      <div className={`stat-value${accent ? ' accent' : ''}`}>{value}</div>
    </div>
  )
}

function InfoRow({ label, value }) {
  return (
    <div className="info-row">
      <span className="info-key">{label}</span>
      <span className="info-value">{value}</span>
    </div>
  )
}

export default function Overview({ view }) {
  return (
    <div className="stats-grid">
      <StatCard icon={<DataUsedIcon />} label="Data Used" value={view.dataUsed} />
      <StatCard icon={<DataLeftIcon />} label="Data Left" value={view.dataLeft} />
      <StatCard icon={<PlanIcon />} label="Plan" value={view.profile} accent />
      <StatCard icon={<DevicesIcon />} label="Devices" value={view.deviceCount} />
    </div>
  )
}

export function AccountPanel({ view }) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title"><AccountIcon />Account</h2>
        <span className={view.overviewBadgeClass}>{view.overviewBadge}</span>
      </div>
      <div className="info-list">
        <InfoRow label="Username" value={view.detailUsername} />
        <InfoRow label="Hostel" value={view.routerName} />
        <InfoRow label="Voucher Status" value={view.accountStatus} />
        <InfoRow label="Login" value={view.loggedInDate} />
        <InfoRow label="Expiry" value={view.expiryDate} />
        <InfoRow label="Data Limit" value={view.dataLimit} />
      </div>
      <div className="footer-note">{view.lastUpdated}</div>
    </div>
  )
}
