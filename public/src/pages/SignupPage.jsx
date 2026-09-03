import { useEffect, useMemo, useState } from 'react'

import { CheckIcon, GlobeIcon, ShieldIcon, WifiIcon } from '../components/Icons'
import { getRouters } from '../services/hotspotApi'

const USERNAME_PATTERN = /^[a-z0-9][a-z0-9._-]{2,63}$/
const PIN_PATTERN = /^[0-9]{6}$/

const INITIAL_FORM = {
  email: '',
  username: '',
  routerId: '',
  pin: '',
  confirmPin: '',
}

function validate(form, routers) {
  const errors = {}
  const email = form.email.trim()
  const username = form.username.trim().toLowerCase()

  if (!email) errors.email = 'Enter your email address.'
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = 'Enter a valid email address.'

  if (!username) errors.username = 'Choose a username.'
  else if (!USERNAME_PATTERN.test(username)) {
    errors.username = 'Use 3-64 lowercase letters, numbers, dots, dashes, or underscores.'
  }

  if (!form.routerId) errors.routerId = 'Select the hostel where you connect.'
  else if (!routers.some((router) => router.router_id === form.routerId)) {
    errors.routerId = 'Select an available hostel.'
  }

  if (!form.pin) errors.pin = 'Create a 6-digit PIN.'
  else if (!PIN_PATTERN.test(form.pin)) errors.pin = 'Your PIN must be exactly 6 digits.'

  if (!form.confirmPin) errors.confirmPin = 'Enter the 6-digit PIN again.'
  else if (form.pin !== form.confirmPin) errors.confirmPin = 'The PINs do not match.'

  return errors
}

function FieldError({ id, message }) {
  if (!message) return null
  return <span className="signup-field-error" id={id}>{message}</span>
}

export default function SignupPage() {
  const [form, setForm] = useState(INITIAL_FORM)
  const [errors, setErrors] = useState({})
  const [routers, setRouters] = useState([])
  const [routersPhase, setRoutersPhase] = useState('loading')
  const [showPin, setShowPin] = useState(false)
  const [showConfirmPin, setShowConfirmPin] = useState(false)
  const [readyMessage, setReadyMessage] = useState('')

  useEffect(() => {
    document.title = 'Create account | FLINT WiFi'
    let active = true

    getRouters()
      .then((items) => {
        if (!active) return
        setRouters(Array.isArray(items) ? items : [])
        setRoutersPhase('loaded')
      })
      .catch(() => {
        if (!active) return
        setRoutersPhase('error')
      })

    return () => {
      active = false
    }
  }, [])

  const selectedRouter = useMemo(
    () => routers.find((router) => router.router_id === form.routerId),
    [form.routerId, routers],
  )

  function updateField(event) {
    const { name, value } = event.target
    let normalizedValue = value
    if (name === 'username') normalizedValue = value.toLowerCase().replace(/\s/g, '')
    if (name === 'pin' || name === 'confirmPin') normalizedValue = value.replace(/\D/g, '')

    setForm((current) => ({ ...current, [name]: normalizedValue }))
    setErrors((current) => ({ ...current, [name]: '' }))
    setReadyMessage('')
  }

  function submit(event) {
    event.preventDefault()
    const nextErrors = validate(form, routers)
    setErrors(nextErrors)
    setReadyMessage('')
    if (Object.keys(nextErrors).length) return

    setReadyMessage(
      `Your details are ready for email verification. ${selectedRouter?.name || 'The selected hostel'} will be tied to this account.`,
    )
  }

  return (
    <main className="signup-page">
      <div className="signup-container">
        <header className="signup-header">
          <a className="signup-brand" href="/" aria-label="Flint WiFi home">
            <span className="signup-logo-mark"><WifiIcon /></span>
            <span>Flint WiFi</span>
          </a>
          <h1>Create your WiFi account</h1>
          <p>Select your hostel and create the login you will use whenever you connect to Flint WiFi.</p>
        </header>

        <section className="signup-card" aria-labelledby="signup-title">
          <div className="signup-card-header">
            <span className="signup-step">Step 1 of 2</span>
            <h2 id="signup-title">Account details</h2>
            <p>We will verify your email before activating your account.</p>
          </div>

          <form className="signup-form" noValidate onSubmit={submit}>
            <div className="signup-field">
              <label htmlFor="signup-email">Email address</label>
              <input
                autoComplete="email"
                className={errors.email ? 'signup-input invalid' : 'signup-input'}
                id="signup-email"
                name="email"
                placeholder="you@example.com"
                type="email"
                value={form.email}
                onChange={updateField}
                aria-describedby={errors.email ? 'signup-email-error' : undefined}
                aria-invalid={Boolean(errors.email)}
              />
              <FieldError id="signup-email-error" message={errors.email} />
            </div>

            <div className="signup-field">
              <label htmlFor="signup-username">Username</label>
              <input
                autoCapitalize="none"
                autoComplete="username"
                className={errors.username ? 'signup-input invalid' : 'signup-input'}
                id="signup-username"
                maxLength={64}
                name="username"
                placeholder="e.g. ama.b"
                spellCheck="false"
                type="text"
                value={form.username}
                onChange={updateField}
                aria-describedby="signup-username-help signup-username-error"
                aria-invalid={Boolean(errors.username)}
              />
              <span className="signup-field-help" id="signup-username-help">This will be your permanent hotspot username.</span>
              <FieldError id="signup-username-error" message={errors.username} />
            </div>

            <div className="signup-field signup-field-wide">
              <div className="signup-label-row">
                <label htmlFor="signup-hostel">Your hostel</label>
                <span>Required</span>
              </div>
              <div className="signup-select-wrap">
                <GlobeIcon />
                <select
                  className={errors.routerId ? 'signup-input signup-select invalid' : 'signup-input signup-select'}
                  disabled={routersPhase === 'loading'}
                  id="signup-hostel"
                  name="routerId"
                  value={form.routerId}
                  onChange={updateField}
                  aria-describedby="signup-hostel-help signup-hostel-error"
                  aria-invalid={Boolean(errors.routerId)}
                >
                  <option value="">
                    {routersPhase === 'loading' ? 'Loading hostels...' : 'Select your hostel'}
                  </option>
                  {routers.map((router) => (
                    <option key={router.router_id} value={router.router_id}>{router.name}</option>
                  ))}
                </select>
              </div>
              <span className="signup-field-help" id="signup-hostel-help">
                Your account will be tied to this hostel&apos;s MikroTik router.
              </span>
              {routersPhase === 'error' && (
                <span className="signup-field-error">Hostels could not be loaded. Start the backend and try again.</span>
              )}
              {routersPhase === 'loaded' && routers.length === 0 && (
                <span className="signup-field-error">No hostels are currently available.</span>
              )}
              <FieldError id="signup-hostel-error" message={errors.routerId} />
            </div>

            <div className="signup-field">
              <label htmlFor="signup-pin">Create 6-digit PIN</label>
              <div className="signup-password-wrap">
                <input
                  autoComplete="new-password"
                  className={errors.pin ? 'signup-input invalid' : 'signup-input'}
                  id="signup-pin"
                  inputMode="numeric"
                  maxLength={6}
                  name="pin"
                  placeholder="6 digits"
                  type={showPin ? 'text' : 'password'}
                  value={form.pin}
                  onChange={updateField}
                  aria-describedby="signup-pin-help signup-pin-error"
                  aria-invalid={Boolean(errors.pin)}
                />
                <button type="button" onClick={() => setShowPin((shown) => !shown)}>{showPin ? 'Hide' : 'Show'}</button>
              </div>
              <span className="signup-field-help" id="signup-pin-help">Use exactly 6 numbers.</span>
              <FieldError id="signup-pin-error" message={errors.pin} />
            </div>

            <div className="signup-field">
              <label htmlFor="signup-confirm-pin">Confirm PIN</label>
              <div className="signup-password-wrap">
                <input
                  autoComplete="new-password"
                  className={errors.confirmPin ? 'signup-input invalid' : 'signup-input'}
                  id="signup-confirm-pin"
                  inputMode="numeric"
                  maxLength={6}
                  name="confirmPin"
                  placeholder="Enter PIN again"
                  type={showConfirmPin ? 'text' : 'password'}
                  value={form.confirmPin}
                  onChange={updateField}
                  aria-describedby={errors.confirmPin ? 'signup-confirm-pin-error' : undefined}
                  aria-invalid={Boolean(errors.confirmPin)}
                />
                <button type="button" onClick={() => setShowConfirmPin((shown) => !shown)}>{showConfirmPin ? 'Hide' : 'Show'}</button>
              </div>
              <FieldError id="signup-confirm-pin-error" message={errors.confirmPin} />
            </div>

            <div className="signup-next-note signup-field-wide">
              <ShieldIcon />
              <p><strong>What happens next?</strong><span>We will email you a verification code, check your hostel router, and then securely create your account.</span></p>
            </div>

            {readyMessage && (
              <div className="signup-ready signup-field-wide" role="status">
                <CheckIcon /><span>{readyMessage}</span>
              </div>
            )}

            <button
              className="signup-submit signup-field-wide"
              disabled={routersPhase !== 'loaded' || routers.length === 0}
              type="submit"
            >
              Continue to email verification
            </button>
          </form>

          <p className="signup-footer-link">Already have an account? <a href="/">Log in</a></p>
        </section>
      </div>
    </main>
  )
}
