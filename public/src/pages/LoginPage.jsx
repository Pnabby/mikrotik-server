import { useEffect, useState } from 'react'

import { WifiIcon } from '../components/Icons'
import { AccountApiError, login } from '../services/accountApi'

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
  const [form, setForm] = useState({ username: '', pin: '' })
  const [errors, setErrors] = useState({})
  const [showPin, setShowPin] = useState(false)
  const [apiError, setApiError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    document.title = 'Log in | FLINT WiFi'
  }, [])

  function updateField(event) {
    const { name, value } = event.target
    const normalizedValue = name === 'username'
      ? value.toLowerCase().replace(/\s/g, '')
      : value.replace(/\D/g, '')

    setForm((current) => ({ ...current, [name]: normalizedValue }))
    setErrors((current) => ({ ...current, [name]: '' }))
    setApiError('')
  }

  async function submit(event) {
    event.preventDefault()
    const nextErrors = validate(form)
    setErrors(nextErrors)
    setApiError('')
    if (Object.keys(nextErrors).length) return

    setBusy(true)
    try {
      const result = await login(form.username, form.pin)
      window.location.assign(result.redirect_to || '/account')
    } catch (error) {
      if (error instanceof AccountApiError && error.status === 401) {
        setApiError('The username or PIN is incorrect.')
      } else if (error instanceof AccountApiError && error.status === 403) {
        setApiError('This account is currently unavailable. Please contact help and support.')
      } else if (error instanceof AccountApiError && error.status === 429) {
        setApiError('Too many login attempts. Please wait before trying again.')
      } else {
        setApiError('Login is temporarily unavailable. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="signup-page">
      <div className="signup-container login-container">
        <header className="signup-header">
          <a className="signup-brand" href="/" aria-label="Flint WiFi home">
            <span className="signup-logo-mark"><WifiIcon /></span>
            <span>Flint WiFi</span>
          </a>
          <h1>Welcome back</h1>
          <p>Log in with your permanent Flint WiFi username and PIN.</p>
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
            </div>

            {apiError && <div className="otp-api-error" role="alert">{apiError}</div>}

            <button className="signup-submit" disabled={busy} type="submit">
              {busy ? 'Logging in...' : 'Log in'}
            </button>
          </form>

          <div className="login-create-account">
            <span>Do not have an account?</span>
            <a href="/signup">Create an account</a>
          </div>
        </section>
      </div>
    </main>
  )
}
