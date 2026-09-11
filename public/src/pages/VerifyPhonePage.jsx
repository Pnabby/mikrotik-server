import { useEffect, useState } from 'react'

import { WifiIcon } from '../components/Icons'
import OtpInput from '../components/OtpInput'
import {
  AccountApiError,
  completePhoneVerification,
  getAccount,
  startPhoneVerification,
} from '../services/accountApi'

const PHONE_PATTERN = /^(?:0\d{9}|233\d{9}|\+233\d{9})$/

export default function VerifyPhonePage() {
  const [phoneNumber, setPhoneNumber] = useState('')
  const [challenge, setChallenge] = useState(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(true)

  useEffect(() => {
    document.title = 'Verify phone | Vlad WiFi'
    getAccount().then((account) => {
      if (account.phone_verified) window.location.replace('/account')
      else {
        setPhoneNumber(account.phone_number || '')
        setBusy(false)
      }
    }).catch(() => window.location.replace('/'))
  }, [])

  async function sendCode(event) {
    event.preventDefault()
    const compact = phoneNumber.replace(/[\s()-]/g, '')
    if (!PHONE_PATTERN.test(compact)) {
      setError('Enter a valid Ghana phone number, for example 024 123 4567.')
      return
    }
    setBusy(true); setError('')
    try {
      setChallenge(await startPhoneVerification(phoneNumber))
      setCode('')
    } catch (err) {
      setError(err instanceof AccountApiError && err.status === 409
        ? 'That phone number is already linked to another account.'
        : err instanceof AccountApiError && err.status === 429
          ? 'Please wait before requesting another code.'
          : 'The SMS could not be sent. Please try again later.')
    } finally { setBusy(false) }
  }

  async function verify(event) {
    event.preventDefault()
    if (!/^\d{6}$/.test(code)) { setError('Enter the 6-digit code from the SMS.'); return }
    setBusy(true); setError('')
    try {
      const result = await completePhoneVerification(challenge.challenge_id, phoneNumber, code)
      window.location.assign(result.redirect_to || '/account')
    } catch (err) {
      setError(err instanceof AccountApiError && err.status === 429
        ? 'Too many incorrect attempts. Request a new code.'
        : 'That code is invalid or has expired.')
    } finally { setBusy(false) }
  }

  return (
    <main className="signup-page">
      <div className="signup-container login-container">
        <header className="signup-header">
          <a className="signup-brand" href="/" aria-label="Vlad WiFi home"><span className="signup-logo-mark"><WifiIcon /></span><span>Vlad WiFi</span></a>
          <h1>Verify your phone</h1>
          <p>Add and verify your mobile number to finish securing your account.</p>
        </header>
        <section className="signup-card login-card">
          <form className="login-form" noValidate onSubmit={challenge ? verify : sendCode}>
            {!challenge ? <div className="signup-field">
              <label htmlFor="verify-phone">Phone number</label>
              <input autoFocus className="signup-input" id="verify-phone" inputMode="tel" type="tel" value={phoneNumber} placeholder="024 123 4567" onChange={(event) => { setPhoneNumber(event.target.value); setError('') }} />
            </div> : <>
              <p>We sent a 6-digit code to <strong>{challenge.destination}</strong>.</p>
              <div className="signup-field">
                <label htmlFor="verify-phone-code">Verification code</label>
                <OtpInput autoFocus id="verify-phone-code" invalid={Boolean(error)} value={code} onChange={(value) => { setCode(value); setError('') }} />
              </div>
            </>}
            {error && <div className="otp-api-error" role="alert">{error}</div>}
            <button className="signup-submit" disabled={busy} type="submit">{busy ? 'Please wait...' : challenge ? 'Verify phone' : 'Send verification code'}</button>
            {challenge && <button className="login-recovery-link" type="button" onClick={() => { setChallenge(null); setCode(''); setError('') }}>Change phone number</button>}
            <p className="auth-legal-links">Your number is handled as described in our <a href="/privacy" target="_blank" rel="noreferrer">Privacy Notice</a>.</p>
          </form>
        </section>
      </div>
    </main>
  )
}
