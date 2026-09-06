import { CheckIcon, DevicesIcon, DeviceTypeIcon, DotIcon, WarningIcon } from './Icons'
import { normalizeIpAddress, normalizeMacAddress, normalizeText } from '../utils/formatters'

function isCurrentSessionDevice(device, session) {
  const deviceIp = normalizeIpAddress(device.ip_address)
  const deviceMac = normalizeMacAddress(device.mac_address)
  const currentIp = normalizeIpAddress(session?.current_device_ip)
  const currentMac = normalizeMacAddress(session?.current_device_mac)
  return Boolean((currentIp && deviceIp === currentIp) || (currentMac && deviceMac === currentMac))
}

function Device({ device, session, onLogout }) {
  const deviceName = normalizeText(device.device_name) || 'Unknown'
  const deviceType = normalizeText(device.device_type) || 'Unknown'
  return (
    <div className="device-item">
      <div className="device-top">
        <div><div className="device-name">{deviceName}</div></div>
        <div className="device-badges">
          {isCurrentSessionDevice(device, session) && (
            <span className="device-status current"><CheckIcon />This device</span>
          )}
          <span className="device-status type"><DeviceTypeIcon type={deviceType} />{deviceType}</span>
          <span className="device-status"><DotIcon />Active</span>
        </div>
      </div>
      <div className="device-metrics">
        <div className="device-metric">
          <div className="device-metric-label">IP</div>
          <div className="device-metric-value">{normalizeText(device.ip_address) || 'N/A'}</div>
        </div>
        <div className="device-metric">
          <div className="device-metric-label">MAC</div>
          <div className="device-metric-value">{normalizeText(device.mac_address) || 'N/A'}</div>
        </div>
        <div className="device-metric full">
          <div className="device-metric-label">Uptime</div>
          <div className="device-metric-value">{normalizeText(device.uptime) || 'N/A'}</div>
        </div>
      </div>
      <div className="device-action">
        <button className="btn-logout" type="button" onClick={() => onLogout(device)}>Logout</button>
      </div>
    </div>
  )
}

export default function DeviceList({ phase, devices, session, onLogout, errorMessage }) {
  if (phase === 'loading') return <div className="empty-state">Loading...</div>
  if (phase === 'error') {
    return <div className="empty-state error"><WarningIcon />{errorMessage || 'Could not load'}</div>
  }
  if (phase !== 'loaded') {
    return <div className="empty-state"><DevicesIcon />Open this page from the WiFi status page to view devices</div>
  }
  if (!devices.length) return <div className="empty-state"><DevicesIcon />No active devices</div>
  return devices.map((device) => (
    <Device key={device.session_id || `${device.mac_address}-${device.ip_address}`} device={device} session={session} onLogout={onLogout} />
  ))
}
