import { useEffect, useState } from 'react'

import { AccountApiError, getAccount, login } from '../services/accountApi'

const USERNAME_PATTERN = /^[a-z0-9]{3,64}$/
const PIN_PATTERN = /^[0-9]{6}$/

function LoginWifiIcon() {
  return (
    <svg viewBox="0 0 96 72" aria-hidden="true">
      <path d="M10 22.5a57 57 0 0 1 76 0" />
      <path d="M23 36.5a38.5 38.5 0 0 1 50 0" />
      <path d="M36 50.5a20 20 0 0 1 24 0" />
      <circle cx="48" cy="63" r="6" />
    </svg>
  )
}

function UserIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 19c.7-3.4 3.2-5.2 7-5.2s6.3 1.8 7 5.2c-1.8 1.2-4.1 1.8-7 1.8S6.8 20.2 5 19Z" />
    </svg>
  )
}

function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="5" y="10" width="14" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </svg>
  )
}

function EyeIcon({ hidden }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M2.5 12s3.4-5.5 9.5-5.5 9.5 5.5 9.5 5.5-3.4 5.5-9.5 5.5S2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="2.5" />
      {hidden && <path d="m4 4 16 16" />}
    </svg>
  )
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12h14M14 7l5 5-5 5" />
    </svg>
  )
}

function validate(form) {
  const errors = {}

  if (!form.username) errors.username = 'Enter your username.'
  else if (!USERNAME_PATTERN.test(form.username)) errors.username = 'Enter a valid username.'

  if (!form.pin) errors.pin = 'Enter your PIN.'
  else if (!PIN_PATTERN.test(form.pin)) errors.pin = 'Enter a valid PIN.'

  return errors
}

export default function LoginPage() {
  const [form, setForm] = useState({ username: '', pin: '', rememberMe: false })
  const [errors, setErrors] = useState({})
  const [showPin, setShowPin] = useState(false)
  const [apiError, setApiError] = useState('')
  const [accountLocked, setAccountLocked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [checkingSession, setCheckingSession] = useState(true)

  useEffect(() => {
    document.title = 'Log in | Vlad WiFi'
    let active = true
    getAccount()
      .then((account) => {
        if (active) window.location.replace(account.phone_verified ? '/account' : '/verify-phone')
      })
      .catch(() => {
        if (active) setCheckingSession(false)
      })
    return () => { active = false }
  }, [])

  function updateField(event) {
    const { name, value, checked, type } = event.target
    if (type === 'checkbox') {
      setForm((current) => ({ ...current, [name]: checked }))
      return
    }
    const normalizedValue = name === 'username'
      ? value.toLowerCase().replace(/\s/g, '')
      : value.replace(/\D/g, '')

    setForm((current) => ({ ...current, [name]: normalizedValue }))
    setErrors((current) => ({ ...current, [name]: '' }))
    setApiError('')
    setAccountLocked(false)
  }

  async function submit(event) {
    event.preventDefault()
    const nextErrors = validate(form)
    setErrors(nextErrors)
    setApiError('')
    setAccountLocked(false)
    if (Object.keys(nextErrors).length) return

    setBusy(true)
    try {
      const result = await login(form.username, form.pin, form.rememberMe)
      window.location.assign(result.redirect_to || '/account')
    } catch (error) {
      if (error instanceof AccountApiError && error.status === 401) {
        setApiError('The username or PIN is incorrect.')
      } else if (error instanceof AccountApiError && error.status === 403) {
        setApiError('This account is currently unavailable. Please contact help and support.')
      } else if (error instanceof AccountApiError && error.status === 423) {
        setApiError('This account is locked after 5 failed login attempts.')
        setAccountLocked(true)
      } else if (error instanceof AccountApiError && error.status === 429) {
        setApiError('Too many login attempts. Please wait before trying again.')
      } else {
        setApiError('Login is temporarily unavailable. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  if (checkingSession) {
    return <main className="signup-page auth-session-check" aria-label="Checking your session" />
  }

  return (
    <main className="signup-page login-page">
      <div className="signup-container login-container">
        <section className="signup-card login-card" aria-labelledby="login-title">
          <header className="login-header">
            <a className="login-brand" href="/" aria-label="Vlad WiFi home">
              <span className="login-logo-mark"><LoginWifiIcon /></span>
              <span className="login-brand-name">Vlad <strong>WiFi</strong></span>
            </a>
            <h1 className="sr-only" id="login-title">Log in to Vlad WiFi</h1>
            <p>Log in with your permanent Vlad WiFi username and PIN.</p>
          </header>

          <form className="login-form" noValidate onSubmit={submit}>
            <div className="signup-field">
              <label htmlFor="login-username">Username</label>
              <div className={`login-input-shell${errors.username ? ' invalid' : ''}`}>
                <span className="login-field-icon"><UserIcon /></span>
                <input autoCapitalize="none" autoComplete="username" id="login-username" maxLength={64} name="username" placeholder="Enter your username" spellCheck="false" type="text" value={form.username} onChange={updateField} aria-describedby={errors.username ? 'login-username-error' : undefined} aria-invalid={Boolean(errors.username)} />
              </div>
              {errors.username && <span className="signup-field-error" id="login-username-error">{errors.username}</span>}
            </div>

            <div className="signup-field">
              <label htmlFor="login-pin">PIN</label>
              <div className={`login-input-shell login-pin-shell${errors.pin ? ' invalid' : ''}`}>
                <span className="login-field-icon"><LockIcon /></span>
                <input
                  autoComplete="off"
                  className={`pin-input${showPin ? '' : ' pin-masked'}`}
                  id="login-pin"
                  inputMode="numeric"
                  maxLength={6}
                  name="pin"
                  placeholder="Enter your PIN"
                  type="text"
                  value={form.pin}
                  onChange={updateField}
                  aria-describedby={errors.pin ? 'login-pin-error' : undefined}
                  aria-invalid={Boolean(errors.pin)}
                />
                <button className="login-pin-toggle" type="button" onClick={() => setShowPin((shown) => !shown)} aria-label={showPin ? 'Hide PIN' : 'Show PIN'} aria-pressed={showPin}><EyeIcon hidden={showPin} /></button>
              </div>
              {errors.pin && <span className="signup-field-error" id="login-pin-error">{errors.pin}</span>}
              <a className="login-recovery-link" href="/forgot-password">Forgot username or PIN?</a>
            </div>

            <label className="auth-checkbox remember-checkbox" htmlFor="remember-me">
              <input
                checked={form.rememberMe}
                id="remember-me"
                name="rememberMe"
                type="checkbox"
                onChange={updateField}
              />
              <span>Remember me on this device</span>
            </label>

            {apiError && <div className="otp-api-error" role="alert">{apiError}</div>}
            {accountLocked && <a className="login-unlock-link" href={`/forgot-password?mode=unlock&username=${encodeURIComponent(form.username)}`}>Unlock account with OTP</a>}

            <button className="signup-submit" disabled={busy} type="submit">
              <span>{busy ? 'Logging in...' : 'Log in'}</span>
              {!busy && <ArrowIcon />}
            </button>
          </form>

          <div className="login-divider" aria-hidden="true"><span>OR</span></div>
          <div className="login-create-account">
            <span>Don&apos;t have an account?</span>
            <a href="/signup">Create an account</a>
          </div>
          <p className="auth-legal-links"><a href="/terms">Terms of Service</a><span>&bull;</span><a href="/privacy">Privacy Policy</a></p>
        </section>
      </div>
    </main>
  )
}
