import { useEffect, useState } from 'react'

import { CheckIcon, LockIcon, ShieldIcon, WifiIcon } from '../components/Icons'
import OtpInput from '../components/OtpInput'
import {
  AccountApiError,
  completeAccountUnlock,
  completePinReset,
  completeUsernameRecovery,
  sendPinResetSms,
  startAccountUnlock,
  startPinReset,
  startUsernameRecovery,
} from '../services/accountApi'
import { normalizeLoginIdentifier, normalizeRecoveryIdentifier } from '../utils/authIdentifiers'

const SIX_DIGITS = /^[0-9]{6}$/

export default function ForgotPinPage({ unlockAccount = false }) {
  const params = new URLSearchParams(window.location.search)
  const isUnlock = unlockAccount || params.get('mode') === 'unlock'
  const [mode, setMode] = useState(isUnlock ? 'unlock' : params.get('mode') === 'username' ? 'username' : 'pin')
  const [step, setStep] = useState('contact')
  const [identifier, setIdentifier] = useState(isUnlock ? params.get('username') || '' : '')
  const [challenge, setChallenge] = useState(null)
  const [form, setForm] = useState({ code: '', newPin: '', confirmation: '' })
  const [errors, setErrors] = useState({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [resendIn, setResendIn] = useState(0)
  const [recoveredUsername, setRecoveredUsername] = useState('')
  const [deliveryMethod, setDeliveryMethod] = useState('email')
  const [showPin, setShowPin] = useState(false)

  useEffect(() => {
    document.title = `${isUnlock ? 'Unlock account' : 'Account recovery'} | Vlad WiFi`
  }, [isUnlock])

  useEffect(() => {
    if (resendIn <= 0) return undefined
    const timer = window.setTimeout(() => setResendIn((remaining) => Math.max(0, remaining - 1)), 1000)
    return () => window.clearTimeout(timer)
  }, [resendIn])

  function clearErrors() {
    setError('')
    setErrors({})
  }

  async function requestCode(event) {
    event?.preventDefault()
    if (busy || (step === 'code' && resendIn > 0)) return
    const normalized = mode === 'unlock'
      ? normalizeLoginIdentifier(identifier)
      : normalizeRecoveryIdentifier(identifier)
    if (!normalized) {
      setErrors({ identifier: mode === 'unlock'
        ? 'Enter the username or phone number for your locked account.'
        : 'Enter your registered email address or phone number.' })
      return
    }
    setBusy(true)
    clearErrors()
    try {
      const result = mode === 'username'
        ? await startUsernameRecovery(normalized)
        : mode === 'unlock'
          ? await startAccountUnlock(normalized)
          : await startPinReset(normalized)
      setIdentifier(normalized)
      setChallenge(result)
      setDeliveryMethod(mode === 'unlock' || normalized.includes('@') ? 'email' : 'sms')
      setForm((current) => ({ ...current, code: '' }))
      setResendIn(result.resend_after_seconds)
      setStep('code')
    } catch (requestError) {
      if (requestError instanceof AccountApiError && requestError.status === 429) {
        setError('Please wait before requesting another code.')
      } else if (mode === 'unlock' && requestError instanceof AccountApiError && requestError.status === 404) {
        setError('We could not find that account. Check your username or phone number.')
      } else if (mode === 'unlock' && requestError instanceof AccountApiError && requestError.status === 409) {
        setError('Your account is not locked. You can return to sign in.')
      } else {
        setError('We could not send your code right now. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  async function useSmsFallback() {
    if (busy) return
    setBusy(true)
    clearErrors()
    try {
      const result = await sendPinResetSms(challenge.challenge_id, identifier)
      setChallenge(result)
      setForm((current) => ({ ...current, code: '' }))
      setDeliveryMethod('sms')
      setResendIn(result.resend_after_seconds)
    } catch (requestError) {
      setError(requestError instanceof AccountApiError && requestError.status === 409
        ? 'SMS recovery requires a verified phone number and can only be used once per code.'
        : 'We could not send an SMS for this request. Please request a new code.')
    } finally {
      setBusy(false)
    }
  }

  function updatePinField(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value.replace(/\D/g, '').slice(0, 6) }))
    setErrors((current) => ({ ...current, [name]: '' }))
    setError('')
  }

  async function completeRecovery(event) {
    event.preventDefault()
    if (busy) return
    const nextErrors = {}
    if (!SIX_DIGITS.test(form.code)) nextErrors.code = 'Enter the 6-digit verification code.'
    if (mode === 'pin' && !SIX_DIGITS.test(form.newPin)) nextErrors.newPin = 'Use exactly 6 digits for your new PIN.'
    if (mode === 'pin' && form.newPin !== form.confirmation) nextErrors.confirmation = 'Your PINs do not match.'
    setErrors(nextErrors)
    setError('')
    if (Object.keys(nextErrors).length) return
    setBusy(true)
    try {
      if (mode === 'username') {
        const result = await completeUsernameRecovery(challenge.challenge_id, identifier, form.code)
        setRecoveredUsername(result.username)
      } else if (mode === 'unlock') {
        await completeAccountUnlock(challenge.challenge_id, identifier, form.code)
      } else {
        await completePinReset(challenge.challenge_id, identifier, form.code, form.newPin, form.confirmation)
      }
      setForm({ code: '', newPin: '', confirmation: '' })
      setStep('done')
    } catch (requestError) {
      if (requestError instanceof AccountApiError && requestError.status === 429) {
        setError('Too many incorrect attempts. Request a new code.')
      } else if (requestError instanceof AccountApiError && requestError.status === 400) {
        setErrors({ code: 'This code is incorrect or has expired. Try again or request a new code.' })
      } else {
        setError('We could not update your account right now. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  function restartRecovery() {
    setStep('contact')
    setChallenge(null)
    setForm({ code: '', newPin: '', confirmation: '' })
    setShowPin(false)
    clearErrors()
  }

  const title = step === 'done'
    ? mode === 'username' ? 'Username recovered' : mode === 'unlock' ? 'Account unlocked' : 'PIN updated'
    : step === 'code'
      ? mode === 'pin' ? 'Set a new PIN' : 'Enter your code'
      : mode === 'unlock' ? 'Unlock your account' : 'Recover your account'

  return (
    <main className="signup-page recovery-page">
      <div className="recovery-container">
        <a className="account-brand recovery-brand" href="/" aria-label="Vlad WiFi home">
          <span><WifiIcon /></span><strong>Vlad WiFi</strong>
        </a>
        <section className="signup-card recovery-card" aria-labelledby="recovery-title">
          <header className="recovery-heading">
            <span className={`recovery-icon${step === 'done' ? ' complete' : ''}`}>
              {step === 'done' ? <CheckIcon /> : mode === 'unlock' ? <LockIcon /> : <ShieldIcon />}
            </span>
            {step !== 'done' && <p className="recovery-step">Step {step === 'contact' ? '1' : '2'} of 2</p>}
            <h1 id="recovery-title">{title}</h1>
            {step === 'contact' && <p>{mode === 'unlock'
              ? 'Your account was locked after too many sign-in attempts. Verify your identity to sign in again.'
              : 'Get back to your WiFi account in a few simple steps.'}</p>}
            {step === 'code' && <p>Enter the code sent {deliveryMethod === 'sms' ? 'by SMS' : 'by email'} to <strong>{challenge.destination}</strong>.</p>}
          </header>

          {step === 'contact' && <>
            {!isUnlock && <div className="recovery-mode-tabs" role="group" aria-label="Choose recovery type">
              <button aria-pressed={mode === 'pin'} className={mode === 'pin' ? 'active' : ''} disabled={busy} type="button" onClick={() => { setMode('pin'); clearErrors() }}>Forgot PIN</button>
              <button aria-pressed={mode === 'username'} className={mode === 'username' ? 'active' : ''} disabled={busy} type="button" onClick={() => { setMode('username'); clearErrors() }}>Forgot username</button>
            </div>}
            <form className="login-form" noValidate onSubmit={requestCode} aria-busy={busy}>
              <div className="signup-field">
                <label htmlFor="recovery-identifier">{isUnlock ? 'Username or phone number' : 'Email or phone number'}</label>
                <input autoCapitalize="none" autoComplete={isUnlock ? 'username' : 'on'} className="signup-input" disabled={busy} id="recovery-identifier" maxLength={isUnlock ? 64 : 320} placeholder={isUnlock ? 'Enter your username or phone' : 'you@example.com or 024 123 4567'} spellCheck="false" type="text" value={identifier} onChange={(event) => { setIdentifier(event.target.value); clearErrors() }} aria-invalid={Boolean(errors.identifier)} aria-describedby={errors.identifier ? 'identifier-error' : 'identifier-help'} />
                {errors.identifier ? <span className="signup-field-error" id="identifier-error">{errors.identifier}</span> : <span className="signup-field-help" id="identifier-help">{isUnlock ? 'We will send a verification code to your registered email.' : 'Use the email or verified phone number linked to your account.'}</span>}
              </div>
              {error && <div className="otp-api-error" role="alert">{error}</div>}
              <button className="signup-submit" disabled={busy} type="submit">{busy ? 'Sending code...' : 'Send verification code'}</button>
            </form>
          </>}

          {step === 'code' && <form className="login-form" noValidate onSubmit={completeRecovery} aria-busy={busy}>
            <div className="signup-field">
              <label htmlFor="recovery-code">Verification code</label>
              <OtpInput id="recovery-code" disabled={busy} invalid={Boolean(errors.code)} describedBy={errors.code ? 'code-error' : 'code-help'} value={form.code} onChange={(code) => { setForm((current) => ({ ...current, code })); setErrors((current) => ({ ...current, code: '' })); setError('') }} />
              {errors.code ? <span className="signup-field-error" id="code-error" role="alert">{errors.code}</span> : <span className="signup-field-help" id="code-help">Enter all 6 digits. You can also paste your code.</span>}
            </div>
            {mode === 'pin' && <div className="recovery-pin-fields">
              <div className="recovery-pin-heading"><span>Your new PIN</span><button type="button" aria-pressed={showPin} onClick={() => setShowPin((shown) => !shown)}>{showPin ? 'Hide PINs' : 'Show PINs'}</button></div>
              <div className="signup-field">
                <label htmlFor="reset-new-pin">New PIN</label>
                <input autoComplete="new-password" className="signup-input" disabled={busy} id="reset-new-pin" inputMode="numeric" maxLength={6} name="newPin" placeholder="Enter 6 digits" type={showPin ? 'text' : 'password'} value={form.newPin} onChange={updatePinField} aria-invalid={Boolean(errors.newPin)} aria-describedby={errors.newPin ? 'new-pin-error' : undefined} />
                {errors.newPin && <span className="signup-field-error" id="new-pin-error" role="alert">{errors.newPin}</span>}
              </div>
              <div className="signup-field">
                <label htmlFor="reset-confirm-pin">Confirm new PIN</label>
                <input autoComplete="new-password" className="signup-input" disabled={busy} id="reset-confirm-pin" inputMode="numeric" maxLength={6} name="confirmation" placeholder="Repeat your new PIN" type={showPin ? 'text' : 'password'} value={form.confirmation} onChange={updatePinField} aria-invalid={Boolean(errors.confirmation)} aria-describedby={errors.confirmation ? 'confirm-pin-error' : undefined} />
                {errors.confirmation && <span className="signup-field-error" id="confirm-pin-error" role="alert">{errors.confirmation}</span>}
              </div>
            </div>}
            {error && <div className="otp-api-error" role="alert">{error}</div>}
            <button className="signup-submit" disabled={busy} type="submit">{busy ? 'Please wait...' : mode === 'username' ? 'Recover username' : mode === 'unlock' ? 'Unlock account' : 'Reset PIN'}</button>
            <div className="otp-actions recovery-code-actions">
              <button disabled={busy || resendIn > 0} type="button" onClick={requestCode}>{resendIn > 0 ? `Resend code in ${resendIn}s` : 'Resend verification code'}</button>
              {mode === 'pin' && deliveryMethod === 'email' && <button disabled={busy} type="button" onClick={useSmsFallback}>Send the code by SMS instead</button>}
              <button disabled={busy} type="button" onClick={restartRecovery}>Use another {isUnlock ? 'username or phone' : 'email or phone'}</button>
            </div>
          </form>}

          {step === 'done' && <div className="recovery-success" role="status">
            {mode === 'username' ? <><p>Your Vlad WiFi username is:</p><strong className="recovered-username">{recoveredUsername}</strong></> : <p>{mode === 'unlock' ? 'Your account is ready. You can now sign in with your username or phone number.' : 'Your PIN has been changed. Sign in with your new PIN to get connected.'}</p>}
            <a className="signup-submit" href="/login">Back to sign in</a>
          </div>}
          {step !== 'done' && <a className="recovery-back-link" href="/login"><span aria-hidden="true">&larr;</span> Back to sign in</a>}
        </section>
        <p className="recovery-help">Need a hand? <a href="#help-and-support" onClick={(event) => { event.preventDefault(); window.dispatchEvent(new Event('vlad:open-support')) }}>Contact support</a></p>
      </div>
    </main>
  )
}
