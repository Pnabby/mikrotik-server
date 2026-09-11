import { useEffect, useState } from 'react'

import { AdminApiError, getAdminSession, login } from './services/adminApi'
import AdminDashboard from './pages/AdminDashboard'

function WifiMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 32 32">
      <path d="M5.5 12.4a15.4 15.4 0 0 1 21 0M9.5 17a9.6 9.6 0 0 1 13 0M13.4 21.5a3.9 3.9 0 0 1 5.2 0" />
      <circle cx="16" cy="25.1" r="1.3" />
    </svg>
  )
}

function EyeIcon({ hidden }) {
  return hidden ? (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M3 3l18 18M10.6 10.7a2 2 0 0 0 2.7 2.7M9.9 4.5A10.5 10.5 0 0 1 12 4.3c5.4 0 9 5.7 9 5.7a15 15 0 0 1-2.2 2.7M6.2 6.2C4.2 7.6 3 10 3 10s3.6 5.7 9 5.7c.7 0 1.4-.1 2-.3" />
    </svg>
  ) : (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M3 12s3.6-5.7 9-5.7S21 12 21 12s-3.6 5.7-9 5.7S3 12 3 12Z" />
      <circle cx="12" cy="12" r="2.5" />
    </svg>
  )
}

function LoginForm({ onAuthenticated }) {
  const [form, setForm] = useState({ username: '', password: '' })
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  function updateField(event) {
    const { name, value } = event.target
    setForm((current) => ({
      ...current,
      [name]: name === 'username' ? value.toLowerCase().replace(/\s/g, '') : value,
    }))
    setError('')
  }

  async function submit(event) {
    event.preventDefault()
    if (!form.username || !form.password) {
      setError('Enter your username and password.')
      return
    }

    setBusy(true)
    setError('')
    try {
      const admin = await login(form.username, form.password)
      onAuthenticated(admin)
    } catch (requestError) {
      if (requestError instanceof AdminApiError && requestError.status === 401) {
        setError('The username or password is incorrect.')
      } else if (requestError instanceof AdminApiError && requestError.status === 403) {
        setError('This administrator account is currently disabled.')
      } else if (requestError instanceof AdminApiError && requestError.status === 429) {
        setError('Too many login attempts. Please wait and try again.')
      } else {
        setError('Admin login is temporarily unavailable. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="admin-login-form" noValidate onSubmit={submit}>
      <div className="admin-field">
        <label htmlFor="admin-username">Username</label>
        <input
          autoCapitalize="none"
          autoComplete="username"
          id="admin-username"
          maxLength={64}
          name="username"
          placeholder="Enter your username"
          spellCheck="false"
          type="text"
          value={form.username}
          onChange={updateField}
        />
      </div>

      <div className="admin-field">
        <div className="admin-label-row">
          <label htmlFor="admin-password">Password</label>
        </div>
        <div className="admin-password-field">
          <input
            autoComplete="current-password"
            id="admin-password"
            maxLength={128}
            minLength={8}
            name="password"
            placeholder="Enter your password"
            type={showPassword ? 'text' : 'password'}
            value={form.password}
            onChange={updateField}
          />
          <button
            aria-label={showPassword ? 'Hide password' : 'Show password'}
            type="button"
            onClick={() => setShowPassword((visible) => !visible)}
          >
            <EyeIcon hidden={showPassword} />
          </button>
        </div>
      </div>

      {error && <div className="admin-form-error" role="alert">{error}</div>}

      <button className="admin-submit" disabled={busy} type="submit">
        {busy ? <span className="admin-button-spinner" /> : null}
        {busy ? 'Signing in...' : 'Sign in'}
      </button>
    </form>
  )
}

export default function App() {
  const [admin, setAdmin] = useState(null)
  const [checkingSession, setCheckingSession] = useState(true)

  useEffect(() => {
    document.title = 'Admin login | Vlad WiFi'
    getAdminSession()
      .then(setAdmin)
      .catch(() => setAdmin(null))
      .finally(() => setCheckingSession(false))
  }, [])

  if (checkingSession) {
    return (
      <main className="admin-loading-page" aria-label="Checking admin session">
        <span className="admin-page-spinner" />
      </main>
    )
  }

  if (admin) return <AdminDashboard admin={admin} onSessionExpired={() => setAdmin(null)} />

  return (
    <main className="admin-auth-page">
      <section className="admin-brand-panel">
        <a className="admin-brand" href="/" aria-label="Vlad WiFi admin home">
          <span><WifiMark /></span>
          <strong>Vlad WiFi</strong>
        </a>

        <div className="admin-brand-copy">
          <span className="admin-shield">
            <svg aria-hidden="true" viewBox="0 0 32 32">
              <path d="M16 3.5 26 7v7.2c0 6.2-4.1 11.7-10 14.3-5.9-2.6-10-8.1-10-14.3V7l10-3.5Z" />
              <path d="m11.7 15.8 2.7 2.7 6.3-6.4" />
            </svg>
          </span>
          <p className="admin-panel-kicker">Secure administration</p>
          <h2>Your network,<br />under control.</h2>
          <p>Sign in to manage Vlad WiFi services from one secure place.</p>
        </div>

        <p className="admin-panel-footer">Protected access · Authorized personnel only</p>
      </section>

      <section className="admin-form-panel">
        <div className="admin-login-card">
          <div className="admin-mobile-brand"><span><WifiMark /></span> Vlad WiFi</div>
          <p className="admin-eyebrow">Administrator portal</p>
          <h1>Welcome back</h1>
          <p className="admin-login-intro">Enter your administrator credentials to continue.</p>
          <LoginForm onAuthenticated={setAdmin} />
          <p className="admin-help-text">Need help accessing your account? Contact your system owner.</p>
        </div>
      </section>
    </main>
  )
}
