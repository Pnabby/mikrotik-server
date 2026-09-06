import { useEffect, useRef, useState } from 'react'

import { AccountIcon, CloseIcon, GlobeIcon, LockIcon, ShieldIcon, VoucherIcon } from './Icons'
import { normalizeText } from '../utils/formatters'

export default function LookupModal({ activeRouterId, error, loading, onClose, onLookup, routers }) {
  const [routerId, setRouterId] = useState(activeRouterId || routers[0]?.router_id || '')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const usernameRef = useRef(null)

  useEffect(() => {
    usernameRef.current?.focus()
  }, [])

  async function submit(event) {
    event.preventDefault()
    if (!normalizeText(routerId) || !normalizeText(username) || !password || loading) return
    const succeeded = await onLookup(username, password, routerId)
    if (succeeded) setPassword('')
  }

  return (
    <div className="modal-backdrop" id="lookup-modal" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <div className="modal lookup-modal" role="dialog" aria-modal="true" aria-labelledby="lookup-modal-title" aria-describedby="lookup-modal-subtitle">
        <div className="modal-header">
          <div className="modal-icon lookup-modal-icon" aria-hidden="true"><VoucherIcon /></div>
          <div className="modal-title-wrap">
            <div className="modal-title" id="lookup-modal-title">Find another voucher</div>
            <div className="modal-subtitle" id="lookup-modal-subtitle">Enter the details printed on the voucher.</div>
          </div>
          <button type="button" className="modal-close" aria-label="Close voucher lookup" onClick={onClose} disabled={loading}><CloseIcon /></button>
        </div>
        <form className="modal-body lookup-form" id="user-lookup-form" onSubmit={submit}>
          <div className="form-field">
            <label htmlFor="lookup-router">WiFi hostel</label>
            <div className="input-shell">
              <GlobeIcon />
              <select className="search-input" id="lookup-router" name="router_id" required value={routerId} onChange={(event) => setRouterId(event.target.value)}>
                {routers.map((router) => <option value={router.router_id} key={router.router_id}>{router.name}</option>)}
              </select>
            </div>
          </div>
          <div className="form-field">
            <label htmlFor="lookup-username">Voucher username</label>
            <div className="input-shell">
              <AccountIcon />
              <input ref={usernameRef} className="search-input" id="lookup-username" name="username" type="text" autoComplete="username" placeholder="Enter username" required value={username} onChange={(event) => setUsername(event.target.value)} />
            </div>
          </div>
          <div className="form-field">
            <label htmlFor="lookup-password">Voucher password</label>
            <div className="input-shell password-field">
              <LockIcon />
              <input className="search-input" id="lookup-password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" placeholder="Enter password" required value={password} onChange={(event) => setPassword(event.target.value)} />
              <button className="password-toggle" id="password-toggle" type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} onClick={() => setShowPassword((value) => !value)}>{showPassword ? 'Hide' : 'Show'}</button>
            </div>
          </div>
          <div className="lookup-privacy-note"><ShieldIcon />Your details are used only to securely retrieve this voucher&apos;s status.</div>
          {error && <div className="modal-error" role="alert">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn btn-outline" onClick={onClose} disabled={loading}>Cancel</button>
            <button className="btn btn-primary" type="submit" disabled={loading}>View voucher details</button>
          </div>
        </form>
      </div>
    </div>
  )
}
