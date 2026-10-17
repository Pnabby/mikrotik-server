import { useState } from 'react'

import { AdminApiError, getOtpSupport, resetOtpLimit } from '../services/adminApi'
import './otp-support.css'

const FLOW_LABELS = {
  registration: 'Signup',
  pin_reset: 'PIN reset',
  username_recovery: 'Username recovery',
  account_unlock: 'Account unlock',
  phone_verification: 'Phone verification',
}

function formatTime(value) {
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'medium' })
}

export default function OtpSupportPanel({ canReset, onSessionExpired }) {
  const [contact, setContact] = useState('')
  const [searchedContact, setSearchedContact] = useState('')
  const [result, setResult] = useState(null)
  const [flow, setFlow] = useState('all')
  const [loading, setLoading] = useState(false)
  const [resetting, setResetting] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const busy = loading || Boolean(resetting)

  function requestError(requestError, resettingLimit = false) {
    if (requestError instanceof AdminApiError && requestError.status === 401) {
      onSessionExpired()
      return
    }
    setError(requestError instanceof AdminApiError && requestError.status === 422
      ? 'Enter the full email address or phone number used for the OTP request.'
      : requestError instanceof AdminApiError && requestError.status === 403
        ? 'Only administrators can reset OTP limits.'
        : resettingLimit
          ? 'The OTP limit could not be reset. Refresh the usage and try again.'
          : 'OTP usage could not be loaded. Please try again.')
  }

  async function lookup(value) {
    if (busy || !value.trim()) return
    setLoading(true)
    setError('')
    setSuccess('')
    setResult(null)
    try {
      setResult(await getOtpSupport(value.trim()))
      setSearchedContact(value.trim())
    } catch (error) {
      requestError(error)
    } finally {
      setLoading(false)
    }
  }

  async function reset(item) {
    if (busy || !canReset || !result?.can_reset) return
    const key = `${item.flow}:${item.subject}`
    setResetting(key)
    setError('')
    setSuccess('')
    try {
      const updated = await resetOtpLimit(item.flow, item.subject)
      setResult((current) => ({ ...current, items: current.items.map((row) => row.flow === item.flow && row.subject === item.subject ? updated : row) }))
      setSuccess(`${FLOW_LABELS[item.flow]} OTP allowance restored for ${item.email || item.phone_number}. Ask the user to request a new code.`)
    } catch (error) {
      requestError(error, true)
    } finally {
      setResetting('')
    }
  }

  const items = result?.items.filter((item) => flow === 'all' || item.flow === flow) || []

  return <section className="otp-support" aria-labelledby="otp-support-title">
    <header className="otp-support-heading">
      <div><p className="dashboard-kicker">Verification assistance</p><h2 id="otp-support-title">OTP support</h2><p>Look up request limits for existing customers and people still signing up.</p></div>
      {result && <button className="otp-support-secondary" disabled={busy} type="button" onClick={() => lookup(searchedContact)}>Refresh usage</button>}
    </header>

    <form className="otp-support-search" onSubmit={(event) => { event.preventDefault(); setFlow('all'); lookup(contact) }} aria-busy={loading}>
      <label htmlFor="otp-support-contact">Email or phone number<input autoCapitalize="none" autoComplete="off" disabled={busy} id="otp-support-contact" maxLength={320} minLength={3} placeholder="you@example.com or 024 123 4567" required spellCheck="false" type="search" value={contact} onChange={(event) => setContact(event.target.value)} /></label>
      <button className="otp-support-primary" disabled={busy || !contact.trim()} type="submit">{loading ? 'Looking up...' : 'Look up OTP usage'}</button>
    </form>
    <p className="otp-support-note">Resetting restores the request allowance for one flow. The user then requests and verifies a fresh code.</p>
    {!canReset && <p className="otp-support-readonly">You can view OTP usage. Resets require an administrator.</p>}
    {error && <p className="otp-support-error" role="alert">{error}</p>}
    {success && <p className="otp-support-success" role="status">{success}</p>}

    {result && <>
      <div className="otp-support-results-heading">
        <p>Usage for <strong>{searchedContact}</strong><small>Checked {formatTime(result.checked_at)}</small></p>
        <div className="otp-support-flow-filter"><label htmlFor="otp-support-flow">Flow</label><select id="otp-support-flow" value={flow} onChange={(event) => setFlow(event.target.value)}><option value="all">All flows</option>{Object.entries(FLOW_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
      </div>
      {!items.length ? <div className="otp-support-empty"><h3>{result.items.length ? 'No requests for this flow' : 'No matching OTP records'}</h3><p>{result.items.length ? 'Choose another flow to see the available records.' : 'Check the email or phone number. Pending signups appear after their first OTP request.'}</p></div> : <div className="otp-support-grid">
        {items.map((item) => {
          const key = `${item.flow}:${item.subject}`
          const blocked = item.requests_remaining === 0
          return <article className="otp-support-card" key={key} aria-label={`${FLOW_LABELS[item.flow]} for ${item.email || item.phone_number}`}>
            <header><h3>{FLOW_LABELS[item.flow]}</h3><span className={`otp-support-status${blocked ? ' limited' : item.next_request_at ? ' waiting' : ''}`}>{blocked ? 'Limit reached' : item.next_request_at ? 'Cooldown' : 'Available'}</span></header>
            <p className="otp-support-person">{item.username || (item.flow === 'registration' ? 'Pending signup' : 'Unregistered contact')}<span>{item.email}</span>{item.phone_number && <span>{item.phone_number}</span>}</p>
            <div className="otp-support-usage"><strong>{item.requests_used} <span>of {item.request_limit} requests used</span></strong><small>In the current hour</small><div className="otp-support-meter" role="meter" aria-label="OTP requests used" aria-valuenow={item.requests_used} aria-valuemin={0} aria-valuemax={Math.max(item.request_limit, item.requests_used)}><i style={{ width: `${Math.min(100, item.requests_used / item.request_limit * 100)}%` }} /></div></div>
            <dl><div><dt>Next request</dt><dd>{item.next_request_at ? <time dateTime={item.next_request_at}>{formatTime(item.next_request_at)}</time> : 'Ready now'}</dd></div><div><dt>Last request</dt><dd>{item.last_requested_at ? <time dateTime={item.last_requested_at}>{formatTime(item.last_requested_at)}</time> : 'No requests yet'}</dd></div></dl>
            {item.last_reset_at && <p className="otp-support-reset-history">Last reset <time dateTime={item.last_reset_at}>{formatTime(item.last_reset_at)}</time><span>By {item.last_reset_by || 'a former administrator'}</span></p>}
            {canReset && result.can_reset && <button className="otp-support-reset" aria-label={`Reset ${FLOW_LABELS[item.flow]} OTP limit for ${item.email || item.phone_number}`} disabled={busy || item.requests_used === 0} type="button" onClick={() => reset(item)}>{resetting === key ? 'Resetting...' : 'Reset OTP limit'}</button>}
          </article>
        })}
      </div>}
    </>}
    {!result && !loading && !error && <div className="otp-support-empty"><h3>Find an OTP request</h3><p>Enter the contact details used during signup or account recovery to check the allowance and next retry time.</p></div>}
  </section>
}
