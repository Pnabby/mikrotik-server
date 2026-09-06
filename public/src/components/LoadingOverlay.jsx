export default function LoadingOverlay({ lookup, longLoading }) {
  const title = longLoading
    ? 'Still working on it'
    : lookup
      ? 'Verifying voucher details'
      : 'Loading voucher details'
  const message = longLoading
    ? 'The network is taking longer than usual to respond. Please keep this page open.'
    : 'Please be patient. Loading your network details can sometimes take a little while.'
  return (
    <div className="loading-overlay" role="status" aria-live="polite" aria-busy="true">
      <div className="loading-card">
        <div className="loading-spinner" aria-hidden="true" />
        <div className="loading-title">{title}</div>
        <div className="loading-message">{message}</div>
        <div className="loading-progress" aria-hidden="true" />
      </div>
    </div>
  )
}
