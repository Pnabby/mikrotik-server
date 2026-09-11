import { useEffect, useState } from 'react'

import { WifiIcon } from '../components/Icons'
import OtpInput from '../components/OtpInput'
import {
  AccountApiError,
  completeAccountUnlock,
  completePinReset,
  completeUsernameRecovery,
  startAccountUnlock,
  startPinReset,
  startUsernameRecovery,
} from '../services/accountApi'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const USERNAME_PATTERN = /^[a-z0-9]{3,64}$/
const SIX_DIGITS = /^[0-9]{6}$/
const recoveryParams = new URLSearchParams(window.location.search)
const requestedMode = recoveryParams.get('mode')
const initialMode = ['username', 'pin', 'unlock'].includes(requestedMode)
  ? requestedMode
  : 'pin'

export default function ForgotPinPage() {
  const [mode, setMode] = useState(initialMode)
  const [step, setStep] = useState('email')
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState(
    (recoveryParams.get('username') || '').toLowerCase().replace(/\s/g, ''),
  )
  const [challenge, setChallenge] = useState(null)
  const [form, setForm] = useState({ code: '', newPin: '', confirmation: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [resendIn, setResendIn] = useState(0)
  const [recoveredUsername, setRecoveredUsername] = useState('')

  useEffect(() => {
    document.title = 'Account recovery | FLINT WiFi'
  }, [])

  useEffect(() => {
    if (resendIn <= 0) return undefined
    const timer = window.setInterval(() => {
      setResendIn((remaining) => Math.max(0, remaining - 1))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [resendIn])

  async function requestCode(event) {
    event?.preventDefault()
    const normalizedEmail = email.trim().toLowerCase()
    const normalizedUsername = username.trim().toLowerCase()
    if (mode === 'unlock' && !USERNAME_PATTERN.test(normalizedUsername)) {
      setError('Enter the username for the locked account.')
      return
    }
    if (mode !== 'unlock' && !EMAIL_PATTERN.test(normalizedEmail)) {
      setError('Enter the email address connected to your account.')
      return
    }
    setBusy(true)
    setError('')
    try {
      let result
      if (mode === 'username') result = await startUsernameRecovery(normalizedEmail)
      else if (mode === 'unlock') result = await startAccountUnlock(normalizedUsername)
      else result = await startPinReset(normalizedEmail)
      if (mode === 'unlock') setUsername(normalizedUsername)
      else setEmail(normalizedEmail)
      setChallenge(result)
      setForm((current) => ({ ...current, code: '' }))
      setResendIn(result.resend_after_seconds)
      setStep('code')
    } catch (requestError) {
      if (requestError instanceof AccountApiError && [502, 503].includes(requestError.status)) {
        setError('Your hostel router is unavailable. No code was sent; please try again later.')
      } else if (requestError instanceof AccountApiError && requestError.status === 429) {
        setError('Please wait before requesting another code.')
      } else if (mode === 'unlock' && requestError instanceof AccountApiError && requestError.status === 404) {
        setError('We could not find an account with that username.')
      } else if (mode === 'unlock' && requestError instanceof AccountApiError && requestError.status === 409) {
        setError('This account is not locked. You can return to login.')
      } else {
        setError('We could not start account recovery. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  function updatePinField(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value.replace(/\D/g, '').slice(0, 6) }))
    setError('')
  }

  async function completeRecovery(event) {
    event.preventDefault()
    if (!SIX_DIGITS.test(form.code)) {
      setError('Enter the 6-digit verification code.')
      return
    }
    if (mode === 'pin' && !SIX_DIGITS.test(form.newPin)) {
      setError('Your new PIN must contain exactly 6 digits.')
      return
    }
    if (mode === 'pin' && form.newPin !== form.confirmation) {
      setError('The new PINs do not match.')
      return
    }
    setBusy(true)
    setError('')
    try {
      if (mode === 'username') {
        const result = await completeUsernameRecovery(challenge.challenge_id, email, form.code)
        setRecoveredUsername(result.username)
      } else if (mode === 'unlock') {
        await completeAccountUnlock(challenge.challenge_id, username, form.code)
      } else {
        await completePinReset(
          challenge.challenge_id,
          email,
          form.code,
          form.newPin,
          form.confirmation,
        )
      }
      setStep('done')
    } catch (requestError) {
      if (requestError instanceof AccountApiError && [502, 503].includes(requestError.status)) {
        setError('Your hostel router is unavailable. No account change was made.')
      } else if (requestError instanceof AccountApiError && requestError.status === 429) {
        setError('Too many incorrect attempts. Request a new code.')
      } else if (requestError instanceof AccountApiError && requestError.status === 400) {
        setError('The code is incorrect or has expired.')
      } else {
        setError('Account recovery could not be completed. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  function chooseMode(nextMode) {
    setMode(nextMode)
    setError('')
  }

  function restartRecovery() {
    setStep('email')
    setChallenge(null)
    setForm({ code: '', newPin: '', confirmation: '' })
    setError('')
  }

  return (
    <main className="signup-page">
      <div className="signup-container login-container">
        <header className="signup-header">
          <a className="signup-brand" href="/" aria-label="Flint WiFi home"><span className="signup-logo-mark"><WifiIcon /></span><span>Flint WiFi</span></a>
          <h1>Recover your account</h1>
          <p>Recover your username, choose a new PIN, or unlock your account.</p>
        </header>

        <section className="signup-card login-card reset-pin-card">
          {step === 'email' && <>
            <div className="signup-card-header"><h2>Find your account</h2><p>We will check your hostel router before sending a verification code.</p></div>
            <div className="recovery-mode-tabs" aria-label="Choose recovery type"><button className={mode === 'username' ? 'active' : ''} type="button" onClick={() => chooseMode('username')}>Forgot username</button><button className={mode === 'pin' ? 'active' : ''} type="button" onClick={() => chooseMode('pin')}>Forgot PIN</button><button className={mode === 'unlock' ? 'active' : ''} type="button" onClick={() => chooseMode('unlock')}>Unlock account</button></div>
            <form className="login-form" noValidate onSubmit={requestCode}>
              {mode === 'unlock'
                ? <div className="signup-field"><label htmlFor="unlock-username">Username</label><input autoCapitalize="none" autoComplete="username" className="signup-input" id="unlock-username" maxLength="64" placeholder="Enter your username" spellCheck="false" type="text" value={username} onChange={(event) => { setUsername(event.target.value.toLowerCase().replace(/\s/g, '')); setError('') }} /></div>
                : <div className="signup-field"><label htmlFor="reset-email">Email address</label><input autoComplete="email" className="signup-input" id="reset-email" placeholder="you@example.com" type="email" value={email} onChange={(event) => { setEmail(event.target.value); setError('') }} /></div>}
              {error && <div className="otp-api-error" role="alert">{error}</div>}
              <button className="signup-submit" disabled={busy} type="submit">{busy ? 'Checking router...' : `Send ${mode === 'username' ? 'username recovery' : mode === 'unlock' ? 'account unlock' : 'PIN reset'} code`}</button>
            </form>
          </>}

          {step === 'code' && <>
            <div className="signup-card-header"><h2>Enter your code</h2><p>A verification code was sent to <strong>{challenge.destination}</strong>.</p></div>
            <form className="login-form" noValidate onSubmit={completeRecovery}>
              <div className="signup-field"><label htmlFor="reset-code">Verification code</label><OtpInput autoFocus id="reset-code" invalid={Boolean(error)} value={form.code} onChange={(value) => { setForm((current) => ({ ...current, code: value })); setError('') }} /></div>
              {mode === 'pin' && <><div className="signup-field"><label htmlFor="reset-new-pin">New PIN</label><input autoComplete="new-password" className="signup-input pin-masked" id="reset-new-pin" inputMode="numeric" maxLength="6" name="newPin" placeholder="6-digit PIN" type="text" value={form.newPin} onChange={updatePinField} /></div><div className="signup-field"><label htmlFor="reset-confirm-pin">Confirm new PIN</label><input autoComplete="new-password" className="signup-input pin-masked" id="reset-confirm-pin" inputMode="numeric" maxLength="6" name="confirmation" placeholder="Repeat new PIN" type="text" value={form.confirmation} onChange={updatePinField} /></div></>}
              {error && <div className="otp-api-error" role="alert">{error}</div>}
              <button className="signup-submit" disabled={busy} type="submit">{busy ? 'Checking router...' : mode === 'username' ? 'Recover username' : mode === 'unlock' ? 'Unlock account' : 'Reset PIN'}</button>
              <div className="otp-actions"><button disabled={busy || resendIn > 0} type="button" onClick={requestCode}>{resendIn > 0 ? `Send another code in ${resendIn}s` : 'Send another code'}</button><button disabled={busy} type="button" onClick={restartRecovery}>Use another {mode === 'unlock' ? 'username' : 'email'}</button></div>
            </form>
          </>}

          {step === 'done' && <div className="reset-pin-success"><span aria-hidden="true">&#10003;</span><h2>{mode === 'username' ? 'Username recovered' : mode === 'unlock' ? 'Account unlocked' : 'PIN changed'}</h2>{mode === 'username' ? <><p>Your Flint WiFi username is:</p><strong className="recovered-username">{recoveredUsername}</strong></> : mode === 'unlock' ? <p>Your account is unlocked and the failed-login counter has been cleared. You can now log in.</p> : <p>Your new PIN is active in Flint and on your hostel router. You can now log in.</p>}<a className="signup-submit" href="/">Return to login</a></div>}
          {step !== 'done' && <p className="reset-back-link"><a href="/">Back to login</a></p>}
        </section>
      </div>
    </main>
  )
}
