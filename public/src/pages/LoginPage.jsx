import { useEffect, useState } from 'react'

import { WifiIcon } from '../components/Icons'
import { AccountApiError, getAccount, login } from '../services/accountApi'

const USERNAME_PATTERN = /^[a-z0-9]{3,64}$/
const PIN_PATTERN = /^[0-9]{6}$/

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
    <main className="signup-page">
      <div className="signup-container login-container">
        <header className="signup-header">
          <a className="signup-brand" href="/" aria-label="Vlad WiFi home">
            <span className="signup-logo-mark"><WifiIcon /></span>
            <span>Vlad WiFi</span>
          </a>
          <h1>Welcome back</h1>
          <p>Log in with your permanent Vlad WiFi username and PIN.</p>
        </header>

        <section className="signup-card login-card" aria-labelledby="login-title">
          <div className="signup-card-header">
            <h2 id="login-title">Log in to your account</h2>
            <p>Enter your account details to continue.</p>
          </div>

          <form className="login-form" noValidate onSubmit={submit}>
            <div className="signup-field">
              <label htmlFor="login-username">Username</label>
              <input
                autoCapitalize="none"
                autoComplete="username"
                className={errors.username ? 'signup-input invalid' : 'signup-input'}
                id="login-username"
                maxLength={64}
                name="username"
                placeholder="Enter your username"
                spellCheck="false"
                type="text"
                value={form.username}
                onChange={updateField}
                aria-describedby={errors.username ? 'login-username-error' : undefined}
                aria-invalid={Boolean(errors.username)}
              />
              {errors.username && <span className="signup-field-error" id="login-username-error">{errors.username}</span>}
            </div>

            <div className="signup-field">
              <label htmlFor="login-pin">PIN</label>
              <div className="signup-password-wrap">
                <input
                  autoComplete="off"
                  className={`${errors.pin ? 'signup-input invalid' : 'signup-input'} pin-input${showPin ? '' : ' pin-masked'}`}
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
                <button type="button" onClick={() => setShowPin((shown) => !shown)}>{showPin ? 'Hide' : 'Show'}</button>
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
              {busy ? 'Logging in...' : 'Log in'}
            </button>
          </form>

          <div className="login-create-account">
            <span>Do not have an account?</span>
            <a href="/signup">Create an account</a>
          </div>
          <p className="auth-legal-links"><a href="/terms">Terms</a><span>&middot;</span><a href="/privacy">Privacy</a></p>
        </section>
      </div>
    </main>
  )
}
