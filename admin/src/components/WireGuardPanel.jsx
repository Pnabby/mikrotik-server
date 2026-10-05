import { useCallback, useEffect, useRef, useState } from 'react'

import { AdminApiError, createWireGuardPeer, forceHostelIpCloudUpdate, getWireGuard, restartHostelRouter, wireGuardPeerAction } from '../services/adminApi'
import { ClientConfigDialog, CreatePeerDialog, RestartRouterDialog } from './VpnDialogs'
import './wireguard.css'

function bytes(value) {
  const amount = Number(value) || 0
  if (amount < 1024) return `${amount} B`
  const unit = Math.min(4, Math.floor(Math.log(amount) / Math.log(1024)))
  return `${(amount / 1024 ** unit).toFixed(1)} ${['B', 'KiB', 'MiB', 'GiB', 'TiB'][unit]}`
}

function handshakeAge(seconds) {
  if (seconds === null) return 'No handshake recorded'
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

function PeerCard({ peer, interfaces, canEdit, busy, onAction, onConfig }) {
  const [keepalive, setKeepalive] = useState(String(peer.keepalive_seconds))
  useEffect(() => setKeepalive(String(peer.keepalive_seconds)), [peer.keepalive_seconds])
  const iface = interfaces.find((item) => item.name === peer.interface)
  const state = peer.disabled ? 'Disabled' : iface?.disabled ? 'Interface disabled'
    : peer.last_handshake_seconds === null ? 'No handshake'
      : peer.last_handshake_seconds <= 180 ? 'Recent handshake' : 'Idle / stale'
  const editable = canEdit && peer.can_manage
  const validKeepalive = /^\d+$/.test(keepalive) && Number(keepalive) <= 65535

  return <article className="vpn-peer">
    <header><div><h3>{peer.name || peer.id}</h3><p>{peer.interface} · {peer.managed_by === 'bth' ? 'Back to Home user' : peer.dynamic ? 'Dynamic peer' : 'WireGuard peer'}</p></div><span className={`vpn-status ${state === 'Recent handshake' ? 'recent' : ''}`}>{state}</span></header>
    <dl className="vpn-peer-details">
      <div><dt>Last handshake</dt><dd>{handshakeAge(peer.last_handshake_seconds)}</dd></div>
      <div><dt>Received / sent</dt><dd>{bytes(peer.rx_bytes)} / {bytes(peer.tx_bytes)}</dd></div>
      <div><dt>Allowed addresses</dt><dd>{peer.allowed_addresses || 'Not reported'}</dd></div>
      <div><dt>Configured endpoint</dt><dd>{peer.endpoint || 'Client initiates connection'}</dd></div>
      <div><dt>Last observed endpoint</dt><dd>{peer.current_endpoint || 'Not reported'}</dd></div>
      <div><dt>Router keepalive</dt><dd>{peer.keepalive_seconds ? `${peer.keepalive_seconds}s` : 'Off'}</dd></div>
      {peer.managed_by === 'bth' && <>
        <div><dt>LAN access</dt><dd>{peer.allow_lan ? 'Allowed' : 'Internet only'}</dd></div>
        <div><dt>BTH active / expiry</dt><dd>{peer.bth_active ? 'Active' : 'Inactive'} · {peer.expires}</dd></div>
      </>}
    </dl>
    <details className="vpn-key"><summary>Peer public key</summary><code>{peer.public_key || 'Not reported'}</code><p>Compare this with the public key of the tunnel on your device. Give each device its own BTH user.</p></details>
    {editable && <div className="vpn-peer-actions">
      <button disabled={busy} type="button" onClick={() => onConfig(peer)}>View QR / config</button>
      <button disabled={busy} type="button" onClick={() => onAction(peer, { action: 'reset' })}>Reset peer</button>
      <button disabled={busy} type="button" onClick={() => onAction(peer, { action: peer.disabled ? 'enable' : 'disable' })}>{peer.disabled ? 'Enable' : 'Disable'}</button>
      {peer.managed_by === 'bth' ? <button disabled={busy} type="button" onClick={() => onAction(peer, { action: 'allow_lan', allow_lan: !peer.allow_lan })}>{peer.allow_lan ? 'Restrict LAN access' : 'Allow LAN access'}</button> : <form onSubmit={(event) => { event.preventDefault(); if (validKeepalive) onAction(peer, { action: 'keepalive', keepalive_seconds: Number(keepalive) }) }}>
        <label>Keepalive (seconds)<input aria-label={`Keepalive for ${peer.name}`} disabled={busy} type="number" min="0" max="65535" step="1" value={keepalive} onChange={(event) => setKeepalive(event.target.value)} /></label>
        <button disabled={busy || !validKeepalive || Number(keepalive) === peer.keepalive_seconds} type="submit">Save</button>
      </form>}
    </div>}
    {!peer.can_manage && <p className="vpn-note">RouterOS manages this dynamic peer. It needs a matching Back to Home user before this page can change it.</p>}
  </article>
}

function RouterVpn({ hostelId, hostels, onSelect, canEdit, onSessionExpired }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [showRestart, setShowRestart] = useState(false)
  const [configPeer, setConfigPeer] = useState(null)
  const [restartPending, setRestartPending] = useState(false)
  const busyRef = useRef(false)
  const active = useRef(true)
  const reading = useRef(false)
  const generation = useRef(0)
  const refreshTimer = useRef(null)
  const restartTimer = useRef(null)

  const read = useCallback(async () => {
    if (reading.current || busyRef.current) return
    reading.current = true
    const currentGeneration = generation.current
    try {
      const result = await getWireGuard(hostelId)
      if (!active.current || currentGeneration !== generation.current) return
      setData(result)
      setError('')
    } catch (requestError) {
      if (!active.current || currentGeneration !== generation.current) return
      if (requestError instanceof AdminApiError && requestError.status === 401) onSessionExpired()
      else setError('Unable to read WireGuard. Check that the server can reach the router API and that its RouterOS account can read WireGuard settings.')
    } finally {
      reading.current = false
      if (active.current) setLoading(false)
    }
  }, [hostelId, onSessionExpired])

  useEffect(() => {
    active.current = true
    read()
    const interval = window.setInterval(read, 15000)
    return () => {
      active.current = false
      window.clearInterval(interval)
      window.clearTimeout(refreshTimer.current)
      window.clearTimeout(restartTimer.current)
    }
  }, [read])

  async function mutate(operation) {
    if (busyRef.current) return
    busyRef.current = true
    generation.current += 1
    setBusy(true)
    setActionError('')
    setMessage('')
    try {
      const result = await operation()
      if (!active.current) return
      setMessage(result.message)
      return result
    } catch (requestError) {
      if (!active.current) return
      if (requestError instanceof AdminApiError && requestError.status === 401) onSessionExpired()
      else if (requestError.code === 'VPN_ACTION_UNCONFIRMED') setActionError('The router action could not be confirmed. It may have run, or the router may have rejected it. Refresh before retrying; check the RouterOS account’s write and script permissions if it persists.')
      else if (requestError.status === 403) setActionError('Your admin account does not have permission to change peers.')
      else if (requestError.status === 404) setActionError('This peer is no longer available. Refresh the list.')
      else if (requestError.code === 'VPN_DUPLICATE_NAME') setActionError('A peer with this device name already exists. Use another name or refresh to view it.')
      else if (requestError.code === 'VPN_ADDRESS_CONFLICT') setActionError('This tunnel address overlaps an existing peer. Choose an unused address.')
      else if (requestError.code === 'VPN_BTH_NOT_RUNNING') setActionError('Back to Home must be running before you can create a device peer. Enable it in WinBox first.')
      else if (requestError.code === 'VPN_INTERFACE_UNAVAILABLE' || requestError.code === 'VPN_USE_BTH') setActionError('Choose an enabled regular WireGuard interface, or create a Back to Home device on the BTH interface.')
      else if (requestError.code === 'VPN_CREATE_UNCONFIRMED') setActionError('Peer creation could not be confirmed. Refresh before creating it again; it may already exist. Check RouterOS support for automatic peer keys and client settings if it failed.')
      else if (requestError.code === 'VPN_RESTART_UNCONFIRMED') {
        setActionError('The restart could not be confirmed. Wait and refresh before trying again; the router may already be restarting. Check its reboot and script permissions.')
        setShowRestart(false)
        pauseAfterRestart()
      }
      else if (requestError.status === 422) setActionError('Check the device name, CIDR addresses, DNS IP, expiry, and endpoint host. Use /32 or /128 for the client tunnel address and leave the port out of the endpoint host.')
      else if (requestError.code === 'VPN_RESTART_CONFIRMATION') setActionError('Type the selected hostel’s name exactly to confirm its restart.')
      else if (requestError.status === 409) setActionError('RouterOS manages this setting. Refresh and use the matching Back to Home user.')
      else setActionError('The action could not be confirmed. Refresh and check router connectivity and API permissions before retrying.')
    } finally {
      if (active.current) {
        // A queued router reset waits two seconds before interrupting the peer.
        window.clearTimeout(refreshTimer.current)
        refreshTimer.current = window.setTimeout(() => {
          busyRef.current = false
          setBusy(false)
          read()
        }, 5000)
      }
    }
  }

  async function perform(peer, payload) {
    const subject = peer ? `“${peer.name || peer.id}”` : 'IP Cloud'
    const confirmations = {
      reset: `Reset ${subject}? The router will disable it briefly, then enable it. This also enables a disabled peer. Its keys stay the same. Your connection may drop briefly.`,
      disable: `Disable ${subject}? Its VPN access will stop. If the server uses this peer to reach the router, you will need another connection to enable it again.`,
      allow_lan: `${payload.allow_lan ? 'Allow' : 'Restrict'} access to the router’s local network for ${subject}? This can affect WinBox and server access.`,
    }
    if (busyRef.current || (confirmations[payload.action] && !window.confirm(confirmations[payload.action]))) return
    await mutate(async () => {
      if (peer) return wireGuardPeerAction(hostelId, peer.id, payload)
      await forceHostelIpCloudUpdate(hostelId)
      return { message: 'IP Cloud refresh requested. Wait a few seconds for the endpoint to update, then reconnect your client.' }
    })
  }

  async function create(payload) {
    const result = await mutate(() => createWireGuardPeer(hostelId, payload))
    if (!result || !active.current) return
    setShowCreate(false)
    if (result.peer_id) setConfigPeer({ id: result.peer_id, name: payload.name })
  }

  async function restart(confirmation) {
    const result = await mutate(() => restartHostelRouter(hostelId, confirmation))
    if (!result || !active.current) return
    setShowRestart(false)
    pauseAfterRestart()
  }

  function pauseAfterRestart() {
    setRestartPending(true)
    window.clearTimeout(restartTimer.current)
    restartTimer.current = window.setTimeout(() => setRestartPending(false), 60000)
  }

  const needle = query.trim().toLowerCase()
  const peers = data?.peers.filter((peer) => [peer.name, peer.interface, peer.public_key, peer.allowed_addresses, peer.current_endpoint].some((value) => value.toLowerCase().includes(needle))) || []
  const controlsBusy = busy || Boolean(error) || restartPending

  return <div className="vpn-panel">
    <header className="dashboard-page-heading">
      <div><p className="dashboard-kicker">Remote access</p><h1>WireGuard &amp; Back to Home</h1><p>Inspect VPN peers and recover access to your hostel router.</p></div>
      <div className="dashboard-heading-actions">
        <div className="hostel-selector"><label htmlFor="vpn-hostel">Selected hostel</label><div><select id="vpn-hostel" disabled={busy} value={hostelId} onChange={(event) => onSelect(event.target.value)}>{hostels.map((hostel) => <option value={hostel.router_id} key={hostel.router_id}>{hostel.name}</option>)}</select></div></div>
        <button className="dashboard-refresh-button" disabled={busy || loading} type="button" onClick={read}>Refresh</button>
        {canEdit && <button className="vpn-danger" disabled={!data || controlsBusy} type="button" onClick={() => { setActionError(''); setShowRestart(true) }}>Restart router</button>}
      </div>
    </header>
    <p className="vpn-note">Updates every 15 seconds. An old handshake can mean an idle device. Activate the tunnel and send traffic before judging whether it works. Recovery controls require the server to reach the router.</p>
    {error && <div className="vpn-alert" role="alert">{error}{data && ' Showing the last successful reading; peer controls are paused until a refresh succeeds.'}</div>}
    {actionError && <div className="vpn-alert" role="alert">{actionError}</div>}
    {message && <div className="vpn-message" role="status">{message}</div>}
    {restartPending && <p className="vpn-note" role="status">Restart was requested. Temporary loss of router access is expected. Changes are paused for one minute while this page checks connectivity; you can select another hostel.</p>}
    {loading && !data && <div className="profiles-loading"><span className="admin-page-spinner" /><p>Reading WireGuard peers…</p></div>}
    {data && <>
      <section className="vpn-cloud">
        <header><div><h2>Back to Home / IP Cloud</h2><p>Router endpoint and relay status</p></div>{canEdit && <button disabled={controlsBusy} type="button" onClick={() => perform(null, { action: 'cloud' })}>Refresh IP Cloud</button>}</header>
        {data.cloud ? <dl className="vpn-peer-details">
          <div><dt>BTH status</dt><dd>{data.cloud.vpn_status}</dd></div>
          <div><dt>VPN endpoint</dt><dd>{data.cloud.vpn_dns_name ? `${data.cloud.vpn_dns_name}:${data.cloud.vpn_port}` : 'Not reported'}</dd></div>
          <div><dt>DDNS name / public IP</dt><dd>{data.cloud.dns_name || 'Not reported'} / {data.cloud.public_address || 'Not reported'}</dd></div>
          <div><dt>Relay / direct reachability</dt><dd>IPv4: {data.cloud.relay_ipv4_status || 'Unknown'} · IPv6: {data.cloud.relay_ipv6_status || 'Unknown'}</dd></div>
        </dl> : <p>IP Cloud information is unavailable.</p>}
        {data.warnings.map((warning) => <p className="vpn-note" key={warning}>{warning}</p>)}
      </section>
      <details className="vpn-help"><summary>Connection checks and recovery steps</summary><ol>
        <li>Deactivate and reactivate the tunnel in WireGuard, then try WinBox again. Refresh here and check for a recent handshake and increasing traffic.</li>
        <li>If there is no handshake, compare the device’s public key with its peer here. Each device should have its own peer; sharing a tunnel between devices can move the endpoint between them.</li>
        <li>Check the BTH user’s expiry and LAN access. Internet-only users may connect but cannot reach WinBox on the LAN. Resetting an expired user does not extend its expiry; create a replacement share in BTH or WinBox.</li>
        <li>Refresh IP Cloud if the public IP or BTH endpoint has changed. Reset the affected peer, wait a few seconds, then reconnect the client. A reset keeps the existing keys.</li>
        <li>For a client behind NAT, try PersistentKeepalive = 25 in that client’s [Peer] settings. The keepalive editor here changes the router side only; BTH manages its dynamic peers.</li>
        <li>A recent handshake with no LAN access points toward AllowedIPs, routes, or firewall rules. Check that WireGuard includes the router’s LAN subnet. The controls here do not rewrite routing or firewall rules.</li>
      </ol><p><a href="https://manual.mikrotik.com/docs/network-management/cloud/back-to-home/" target="_blank" rel="noreferrer">MikroTik Back to Home guide</a> · <a href="https://manual.mikrotik.com/docs/virtual-private-networks/wireguard/" target="_blank" rel="noreferrer">WireGuard guide</a></p></details>
      <section className="vpn-interface-list" aria-label="WireGuard interfaces">{data.interfaces.map((iface) => <details key={iface.name}><summary><strong>{iface.name}</strong><span>UDP {iface.listen_port} · {iface.disabled ? 'Disabled' : iface.running ? 'Running' : 'Not running'}</span></summary><p>MTU {iface.mtu}</p><p>Router public key <code>{iface.public_key || 'Not reported'}</code></p></details>)}</section>
      <div className="vpn-list-heading"><h2>Peers ({data.peers.length})</h2><div><input aria-label="Search WireGuard peers" placeholder="Search name, key, address…" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />{canEdit && <button className="vpn-primary" disabled={controlsBusy} type="button" onClick={() => { setActionError(''); setShowCreate(true) }}>Create peer</button>}</div></div>
      {!data.peers.length ? <div className="profiles-empty"><h3>No WireGuard peers</h3><p>This router has no WireGuard peers or Back to Home users available to this API account.</p></div> : !peers.length ? <p>No peers match your search.</p> : <div className="vpn-peer-grid">{peers.map((peer) => <PeerCard key={peer.id} peer={peer} interfaces={data.interfaces} canEdit={canEdit} busy={controlsBusy} onAction={perform} onConfig={setConfigPeer} />)}</div>}
      {!canEdit && <p className="vpn-note">Your account has view access. An operator or administrator can change peers.</p>}
      <p className="vpn-note">Last read: {new Date(data.generated_at).toLocaleString()}</p>
    </>}
    {showCreate && data && <CreatePeerDialog data={data} busy={busy} error={actionError} onClose={() => setShowCreate(false)} onCreate={create} />}
    {showRestart && <RestartRouterDialog name={hostels.find((hostel) => hostel.router_id === hostelId)?.name || data?.router_name || hostelId} busy={busy} error={actionError} onClose={() => setShowRestart(false)} onRestart={restart} />}
    {configPeer && <ClientConfigDialog hostelId={hostelId} peer={configPeer} onClose={() => setConfigPeer(null)} onSessionExpired={onSessionExpired} />}
  </div>
}

export default function WireGuardPanel({ hostels, loadingHostels, selectedId, onSelect, canEdit, onSessionExpired }) {
  const available = hostels.filter((hostel) => hostel.is_active && hostel.hotspot_network)
  const hostelId = available.some((hostel) => hostel.router_id === selectedId) ? selectedId : available[0]?.router_id
  if (loadingHostels) return <div className="profiles-loading"><p>Loading hostels…</p></div>
  if (!hostelId) return <div className="profiles-empty"><h1>WireGuard &amp; Back to Home</h1><p>Add an active hostel with its VPN host and hotspot network to inspect its VPN peers.</p></div>
  return <RouterVpn key={hostelId} hostelId={hostelId} hostels={available} onSelect={onSelect} canEdit={canEdit} onSessionExpired={onSessionExpired} />
}
