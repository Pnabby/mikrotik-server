import { useEffect, useId, useRef, useState } from 'react'
import QRCode from 'qrcode'

import { getWireGuardClientConfig } from '../services/adminApi'

function VpnDialog({ title, children, busy = false, onClose }) {
  const dialog = useRef(null)
  const titleId = useId()
  useEffect(() => {
    const element = dialog.current
    element.showModal()
    return () => element.close()
  }, [])
  return <dialog className="vpn-dialog" ref={dialog} aria-labelledby={titleId} onCancel={(event) => { event.preventDefault(); if (!busy) onClose() }}>
    <header><h2 id={titleId}>{title}</h2><button aria-label="Close dialog" disabled={busy} type="button" onClick={onClose}>×</button></header>
    {children}
  </dialog>
}

export function CreatePeerDialog({ data, busy, error, onClose, onCreate }) {
  const interfaces = data.interfaces.filter((iface) => !iface.disabled && iface.name !== 'back-to-home-vpn')
  const [form, setForm] = useState({
    kind: 'bth', name: '', interface: interfaces[0]?.name || '', client_addresses: '',
    client_endpoint: data.cloud?.dns_name || data.cloud?.public_address || '',
    client_allowed_addresses: '0.0.0.0/0,::/0', client_dns: '', client_keepalive: '25',
    allow_lan: true, expires_days: '',
  })
  function change(event) {
    const { name, type, checked, value } = event.target
    setForm((current) => ({ ...current, [name]: type === 'checkbox' ? checked : value }))
  }
  function submit(event) {
    event.preventDefault()
    const payload = {
      kind: form.kind, name: form.name.trim(),
      client_allowed_addresses: form.client_allowed_addresses.trim(), client_dns: form.client_dns.trim(),
      ...(form.kind === 'bth' ? { allow_lan: form.allow_lan, expires_days: form.expires_days ? Number(form.expires_days) : null }
        : { interface: form.interface, client_addresses: form.client_addresses.trim(), client_endpoint: form.client_endpoint.trim(), client_keepalive: Number(form.client_keepalive) }),
    }
    onCreate(payload)
  }
  return <VpnDialog title="Create a VPN peer" busy={busy} onClose={onClose}>
    <form className="vpn-create-form" onSubmit={submit}>
      <p>Give each device its own peer. The router generates its keys; you can then import its QR code or .conf file.</p>
      {error && <div className="vpn-alert" role="alert">{error}</div>}
      <fieldset disabled={busy}>
        <label>Peer type<select name="kind" value={form.kind} onChange={change}><option value="bth">Back to Home device</option><option value="wireguard">Regular WireGuard peer</option></select></label>
        <label>Device name<input autoFocus required maxLength="64" name="name" placeholder="e.g. My laptop" value={form.name} onChange={change} /></label>
        {form.kind === 'bth' ? <>
          <label className="vpn-checkbox"><input type="checkbox" name="allow_lan" checked={form.allow_lan} onChange={change} />Allow access to the local network / WinBox</label>
          <label>Expires after (days)<input type="number" min="1" max="3650" step="1" name="expires_days" placeholder="Leave empty for no expiry" value={form.expires_days} onChange={change} /></label>
          {data.cloud?.vpn_status !== 'running' && <p className="vpn-note">Back to Home must be running on the router before you can add a device.</p>}
        </> : <>
          <label>WireGuard interface<select required name="interface" value={form.interface} onChange={change}>{!interfaces.length && <option value="">No enabled regular interface</option>}{interfaces.map((iface) => <option value={iface.name} key={iface.name}>{iface.name} · UDP {iface.listen_port}</option>)}</select></label>
          <label>Client tunnel address<input required maxLength="255" name="client_addresses" placeholder="e.g. 10.0.0.2/32" value={form.client_addresses} onChange={change} /><small>Use an unused address in this interface’s VPN subnet, with /32 for IPv4 or /128 for IPv6.</small></label>
          <label>Router endpoint host<input required maxLength="255" name="client_endpoint" placeholder="Public IP or DNS name, without a port" value={form.client_endpoint} onChange={change} /><small>The interface’s UDP listen port is appended automatically.</small></label>
          <label>Client keepalive (seconds)<input required type="number" min="0" max="65535" step="1" name="client_keepalive" value={form.client_keepalive} onChange={change} /></label>
          <p className="vpn-note">This uses the existing interface, routes, and firewall. The endpoint must be reachable by your device. RouterOS must support automatic peer keys and client export settings; use BTH when you need its relay.</p>
        </>}
        <label>Client AllowedIPs<input required maxLength="1024" name="client_allowed_addresses" value={form.client_allowed_addresses} onChange={change} /><small>These are the networks routed through the VPN. The default routes all traffic; use your LAN subnet for LAN-only access.</small></label>
        <label>Client DNS server (optional)<input maxLength="255" name="client_dns" placeholder="e.g. 1.1.1.1" value={form.client_dns} onChange={change} /></label>
      </fieldset>
      <footer><button disabled={busy} type="button" onClick={onClose}>Cancel</button><button className="vpn-primary" disabled={busy || (form.kind === 'wireguard' && !interfaces.length)} type="submit">{busy ? 'Creating…' : 'Create peer'}</button></footer>
    </form>
  </VpnDialog>
}

export function RestartRouterDialog({ name, busy, error, onClose, onRestart }) {
  const [confirmation, setConfirmation] = useState('')
  return <VpnDialog title={`Restart ${name}?`} busy={busy} onClose={onClose}>
    <form className="vpn-create-form" onSubmit={(event) => { event.preventDefault(); if (confirmation === name) onRestart(confirmation) }}>
      <p>Everyone using this router will lose WiFi internet and VPN access while it restarts. Its configuration will be kept.</p>
      {error && <div className="vpn-alert" role="alert">{error}</div>}
      <label>Type {name} to confirm<input autoFocus required autoComplete="off" disabled={busy} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>
      <footer><button disabled={busy} type="button" onClick={onClose}>Cancel</button><button className="vpn-danger" disabled={busy || confirmation !== name} type="submit">{busy ? 'Requesting restart…' : 'Restart router'}</button></footer>
    </form>
  </VpnDialog>
}

export function ClientConfigDialog({ hostelId, peer, onClose, onSessionExpired }) {
  const [data, setData] = useState(null)
  const [qr, setQr] = useState('')
  const [error, setError] = useState('')
  const [qrError, setQrError] = useState('')
  const [copyMessage, setCopyMessage] = useState('')
  useEffect(() => {
    let active = true
    async function load() {
      try {
        const result = await getWireGuardClientConfig(hostelId, peer.id)
        if (!active) return
        setData(result)
        try {
          const png = await QRCode.toDataURL(result.config, { errorCorrectionLevel: 'M', margin: 4, width: 360 })
          if (active) setQr(png)
        } catch {
          if (active) setQrError('This configuration is too large for a QR code. Download the .conf file instead.')
        }
      } catch (requestError) {
        if (!active) return
        if (requestError.status === 401) onSessionExpired()
        else if (requestError.status === 403) setError('Only operators and administrators can view client credentials.')
        else if (requestError.code === 'VPN_CONFIG_UNAVAILABLE') setError('The router cannot export a complete client configuration. An existing device’s private key cannot be recovered from its public key. If RouterOS stored the key, check its sensitive permission and client address/endpoint settings. You can create a separate BTH peer for this device.')
        else setError('The configuration could not be read. Check router connectivity, RouterOS support for client export, and the API account’s sensitive permission.')
      }
    }
    load()
    return () => { active = false }
  }, [hostelId, peer.id, onSessionExpired])

  function download() {
    const blob = new Blob([data.config], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${data.name.replace(/[^a-zA-Z0-9_-]+/g, '-').slice(0, 64) || 'wireguard'}.conf`
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return <VpnDialog title={`Client configuration · ${peer.name}`} onClose={onClose}>
    <p className="vpn-note">This QR code and file contain this device’s VPN credentials. Import them on that device using the WireGuard app.</p>
    {error ? <div className="vpn-alert" role="alert">{error}</div> : !data ? <p role="status">Reading client configuration…</p> : <>
      {qr ? <figure className="vpn-qr"><img width="360" height="360" src={qr} alt={`WireGuard QR code for ${data.name}`} /><figcaption>In WireGuard, choose “Scan from QR code”.</figcaption></figure> : qrError ? <p className="vpn-alert" role="alert">{qrError}</p> : <p role="status">Generating QR code…</p>}
      <details className="vpn-config-text"><summary>View configuration text</summary><textarea aria-label="WireGuard client configuration" readOnly spellCheck="false" value={data.config} /></details>
      <footer><button type="button" onClick={download}>Download .conf</button>{qr && <a className="vpn-download-qr" href={qr} download="wireguard-qr.png">Download QR</a>}<button type="button" onClick={async () => {
        try { await navigator.clipboard.writeText(data.config); setCopyMessage('Configuration copied.') }
        catch { setCopyMessage('Copy failed. Use the configuration text or download the file.') }
      }}>Copy config</button></footer>
      {copyMessage && <p role="status" className="vpn-note">{copyMessage}</p>}
    </>}
  </VpnDialog>
}
