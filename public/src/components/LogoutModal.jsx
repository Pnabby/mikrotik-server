import { CloseIcon, WarningIcon } from './Icons'
import { normalizeText } from '../utils/formatters'

export default function LogoutModal({ device, error, loading, username, onClose, onConfirm }) {
  return (
    <div className="modal-backdrop" id="logout-modal" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="logout-modal-title">
        <div className="modal-header">
          <div className="modal-icon" aria-hidden="true"><WarningIcon /></div>
          <div className="modal-title-wrap">
            <div className="modal-title" id="logout-modal-title">Confirm device logout</div>
            <div className="modal-subtitle">This will immediately disconnect the selected device from the hotspot session.</div>
          </div>
          <button type="button" className="modal-close" aria-label="Close confirmation" onClick={onClose} disabled={loading}><CloseIcon /></button>
        </div>
        <div className="modal-body">
          <div className="modal-card">
            <div className="modal-device">{normalizeText(device.device_name) || 'Unknown device'}</div>
            <div className="modal-user">User: {username || '--'}</div>
            <div className="modal-meta">
              <div className="modal-meta-row"><span className="modal-meta-label">IP address</span><span className="modal-meta-value">{normalizeText(device.ip_address) || 'N/A'}</span></div>
              <div className="modal-meta-row"><span className="modal-meta-label">MAC address</span><span className="modal-meta-value">{normalizeText(device.mac_address) || 'N/A'}</span></div>
            </div>
          </div>
          <div className="modal-warning">The device will need to authenticate again before it can reconnect.</div>
          {error && <div className="modal-error">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn btn-outline" onClick={onClose} disabled={loading}>Cancel</button>
            <button type="button" className="btn btn-danger" onClick={onConfirm} disabled={loading}>{loading ? 'Logging out...' : error ? 'Try again' : 'Confirm logout'}</button>
          </div>
        </div>
      </div>
    </div>
  )
}
