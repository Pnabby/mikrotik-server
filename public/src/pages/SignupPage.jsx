import { useEffect, useState } from 'react'

import { CheckIcon, GlobeIcon, ShieldIcon, WifiIcon } from '../components/Icons'
import OtpInput from '../components/OtpInput'
import { getRouters } from '../services/hotspotApi'
import {
  completeRegistration,
  getRegistrationRouterReadiness,
  getUsernameAvailability,
  RegistrationApiError,
  startRegistration,
} from '../services/registrationApi'

const USERNAME_PATTERN = /^[a-z0-9]{3,64}$/
const PIN_PATTERN = /^[0-9]{6}$/

const INITIAL_FORM = {
  email: '',
  phoneNumber: '',
  username: '',
  routerId: '',
  pin: '',
  confirmPin: '',
  acceptedTerms: false,
}

function validate(form, routers) {
  const errors = {}
  const email = form.email.trim()
  const username = form.username.trim().toLowerCase()

  if (!email) errors.email = 'Enter your email address.'
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = 'Enter a valid email address.'

  const phone = form.phoneNumber.replace(/[\s()-]/g, '')
  if (!phone) errors.phoneNumber = 'Enter your phone number.'
  else if (!/^(?:0\d{9}|233\d{9}|\+233\d{9})$/.test(phone)) errors.phoneNumber = 'Enter a valid Ghana phone number.'

  if (!username) errors.username = 'Choose a username.'
  else if (!USERNAME_PATTERN.test(username)) {
    errors.username = 'Use 3-64 lowercase letters and numbers only.'
  }

  if (!form.routerId) errors.routerId = 'Select the hostel where you connect.'
  else if (!routers.some((router) => router.router_id === form.routerId)) {
    errors.routerId = 'Select an available hostel.'
  }

  if (!form.pin) errors.pin = 'Create a 6-digit PIN.'
  else if (!PIN_PATTERN.test(form.pin)) errors.pin = 'Your PIN must be exactly 6 digits.'

  if (!form.confirmPin) errors.confirmPin = 'Enter the 6-digit PIN again.'
  else if (form.pin !== form.confirmPin) errors.confirmPin = 'The PINs do not match.'

  if (!form.acceptedTerms) errors.acceptedTerms = 'Accept the Terms and Conditions to continue.'

  return errors
}

function FieldError({ id, message }) {
  if (!message) return null
  return <span className="signup-field-error" id={id}>{message}</span>
}

function SignupHeader() {
  return (
    <header className="signup-header">
      <a className="signup-brand" href="/" aria-label="Vlad WiFi home">
        <span className="signup-logo-mark"><WifiIcon /></span>
        <span>Vlad WiFi</span>
      </a>
      <h1>Create your WiFi account</h1>
      <p>Select your hostel and create the login you will use whenever you connect to Vlad WiFi.</p>
    </header>
  )
}

function startErrorMessage(error) {
  if (!(error instanceof RegistrationApiError)) return 'Could not send the SMS code. Check your connection and try again.'
  if (error.status === 409) return 'That email address or username is already registered.'
  if (error.status === 429) return 'Too many codes were requested. Please wait before trying again.'
  if ([404, 502, 503].includes(error.status)) {
    return 'Signup is currently unavailable. Please contact help and support.'
  }
  return 'Could not send the SMS verification code. Please try again.'
}

function verifyErrorMessage(error) {
  if (!(error instanceof RegistrationApiError)) return 'Could not verify the code. Check your connection and try again.'
  if (error.status === 400) return 'That code is invalid or has expired. Check it or request a new one.'
  if (error.status === 403) return 'This hostel is not currently accepting registrations.'
  if (error.status === 409) return 'That username or email is already in use. Change your account details.'
  if (error.status === 429) return 'Too many incorrect attempts. Request a new verification code.'
  if (error.status === 502 || error.status === 503) {
    return 'Signup is currently unavailable. Your account was not created. Please contact help and support.'
  }
  return 'Could not complete your registration. Your account was not created; please try again.'
}

export default function SignupPage() {
  const [form, setForm] = useState(INITIAL_FORM)
  const [errors, setErrors] = useState({})
  const [routers, setRouters] = useState([])
  const [routersPhase, setRoutersPhase] = useState('loading')
  const [showPin, setShowPin] = useState(false)
  const [showConfirmPin, setShowConfirmPin] = useState(false)
  const [step, setStep] = useState('details')
  const [challenge, setChallenge] = useState(null)
  const [completedAccount, setCompletedAccount] = useState(null)
  const [usernameAvailability, setUsernameAvailability] = useState({
    phase: 'idle',
    username: '',
    suggestions: [],
  })
  const [routerReadiness, setRouterReadiness] = useState({
    phase: 'idle',
    routerId: '',
    username: '',
  })
  const [otpCode, setOtpCode] = useState('')
  const [otpError, setOtpError] = useState('')
  const [apiError, setApiError] = useState('')
  const [busy, setBusy] = useState(false)
  const [resendSeconds, setResendSeconds] = useState(0)

  useEffect(() => {
    document.title = 'Create account | Vlad WiFi'
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

  useEffect(() => {
    if (step !== 'otp' || resendSeconds <= 0) return undefined
    const timer = window.setTimeout(() => {
      setResendSeconds((seconds) => Math.max(0, seconds - 1))
    }, 1000)
    return () => window.clearTimeout(timer)
  }, [resendSeconds, step])

  useEffect(() => {
    const username = form.username.trim().toLowerCase()
    if (step !== 'details' || !USERNAME_PATTERN.test(username)) {
      setUsernameAvailability({ phase: 'idle', username: '', suggestions: [] })
      return undefined
    }

    const controller = new AbortController()
    let active = true
    setUsernameAvailability({ phase: 'checking', username, suggestions: [] })
    const timer = window.setTimeout(() => {
      getUsernameAvailability(username, controller.signal)
        .then((result) => {
          if (!active) return
          setUsernameAvailability({
            phase: result.available ? 'available' : 'unavailable',
            username: result.username,
            suggestions: result.suggestions || [],
          })
        })
        .catch((error) => {
          if (active && error.name !== 'AbortError') {
            setUsernameAvailability({ phase: 'error', username, suggestions: [] })
          }
        })
    }, 350)

    return () => {
      active = false
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [form.username, step])

  useEffect(() => {
    const username = form.username.trim().toLowerCase()
    const routerId = form.routerId
    const databaseUsernameIsAvailable = (
      usernameAvailability.phase === 'available' &&
      usernameAvailability.username === username
    )
    if (
      step !== 'details' ||
      !routerId ||
      !USERNAME_PATTERN.test(username) ||
      !databaseUsernameIsAvailable
    ) {
      setRouterReadiness({ phase: 'idle', routerId: '', username: '' })
      return undefined
    }

    const controller = new AbortController()
    let active = true
    setRouterReadiness({ phase: 'checking', routerId, username })
    const timer = window.setTimeout(() => {
      getRegistrationRouterReadiness(routerId, username, controller.signal)
        .then(() => {
          if (!active) return
          setRouterReadiness({ phase: 'ready', routerId, username })
        })
        .catch((error) => {
          if (!active || error.name === 'AbortError') return
          setRouterReadiness({
            phase: error.status === 409 ? 'username-taken' : 'unavailable',
            routerId,
            username,
          })
        })
    }, 250)

    return () => {
      active = false
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [form.routerId, form.username, step, usernameAvailability])

  function updateField(event) {
    const { name, value, checked, type } = event.target
    if (type === 'checkbox') {
      setForm((current) => ({ ...current, [name]: checked }))
      setErrors((current) => ({ ...current, [name]: '' }))
      setApiError('')
      return
    }
    let normalizedValue = value
    if (name === 'username') normalizedValue = value.toLowerCase().replace(/[^a-z0-9]/g, '')
    if (name === 'pin' || name === 'confirmPin') normalizedValue = value.replace(/\D/g, '')
    if (name === 'phoneNumber') normalizedValue = value.replace(/[^\d+\s()-]/g, '')

    setForm((current) => ({ ...current, [name]: normalizedValue }))
    setErrors((current) => ({ ...current, [name]: '' }))
    setApiError('')
  }

  async function requestCode() {
    setBusy(true)
    setApiError('')
    try {
      const result = await startRegistration({
        email: form.email.trim().toLowerCase(),
        phone_number: form.phoneNumber,
        username: form.username.trim().toLowerCase(),
        router_id: form.routerId,
        pin: form.pin,
        accepted_terms: form.acceptedTerms,
      })
      setChallenge(result)
      setOtpCode('')
      setOtpError('')
      setResendSeconds(result.resend_after_seconds || 60)
      setStep('otp')
    } catch (error) {
      setApiError(startErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  async function submit(event) {
    event.preventDefault()
    const nextErrors = validate(form, routers)
    if (usernameAvailability.phase === 'unavailable') {
      nextErrors.username = 'That username is already taken. Choose another one.'
    }
    setErrors(nextErrors)
    setApiError('')
    if (Object.keys(nextErrors).length) return

    await requestCode()
  }

  function chooseSuggestedUsername(username) {
    setForm((current) => ({ ...current, username }))
    setErrors((current) => ({ ...current, username: '' }))
    setApiError('')
  }

  async function verifyOtp(event) {
    event.preventDefault()
    if (!PIN_PATTERN.test(otpCode)) {
      setOtpError('Enter the 6-digit code from the SMS.')
      return
    }

    setBusy(true)
    setOtpError('')
    setApiError('')
    try {
      const completed = await completeRegistration(
        challenge.challenge_id,
        {
          email: form.email.trim().toLowerCase(),
          phone_number: form.phoneNumber,
          username: form.username.trim().toLowerCase(),
          router_id: form.routerId,
          pin: form.pin,
          accepted_terms: form.acceptedTerms,
        },
        otpCode,
      )
      setCompletedAccount(completed)
      setForm((current) => ({ ...current, pin: '', confirmPin: '' }))
      setOtpCode('')
      setStep('verified')
    } catch (error) {
      setOtpError(verifyErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  async function resendOtp() {
    if (resendSeconds > 0 || busy) return
    await requestCode()
  }

  function editDetails() {
    setStep('details')
    setOtpCode('')
    setOtpError('')
    setApiError('')
  }

  if (step === 'otp') {
    return (
      <main className="signup-page">
        <div className="signup-container">
          <SignupHeader />

          <section className="signup-card otp-card" aria-labelledby="otp-title">
            <div className="signup-card-header">
              <span className="signup-step">Step 2 of 2</span>
              <h2 id="otp-title">Check your phone</h2>
              <p>We sent a 6-digit verification code to <strong>{challenge.destination}</strong>.</p>
            </div>

            <form className="otp-form" noValidate onSubmit={verifyOtp}>
              <div className="signup-field">
                <label htmlFor="signup-otp">Verification code</label>
                <OtpInput
                  autoFocus
                  id="signup-otp"
                  invalid={Boolean(otpError)}
                  value={otpCode}
                  onChange={(value) => { setOtpCode(value); setOtpError('') }}
                />
                <span className="signup-field-help" id="signup-otp-help">
                  The code expires in {Math.ceil((challenge.expires_in_seconds || 600) / 60)} minutes.
                </span>
                <FieldError id="signup-otp-error" message={otpError} />
              </div>

              {apiError && <div className="otp-api-error" role="alert">{apiError}</div>}

              <button className="signup-submit" disabled={busy} type="submit">
                {busy ? 'Verifying...' : 'Verify phone'}
              </button>

              <div className="otp-actions">
                <button disabled={busy || resendSeconds > 0} type="button" onClick={resendOtp}>
                  {resendSeconds > 0 ? `Resend code in ${resendSeconds}s` : 'Resend code'}
                </button>
                <button disabled={busy} type="button" onClick={editDetails}>Change account details</button>
              </div>
            </form>
          </section>
        </div>
      </main>
    )
  }

  if (step === 'verified') {
    return (
      <main className="signup-page">
        <div className="signup-container">
          <SignupHeader />

          <section className="signup-card otp-card otp-complete" aria-labelledby="verified-title">
            <span className="otp-success-icon"><CheckIcon /></span>
            <span className="signup-step">Phone verified</span>
            <h2 id="verified-title">Account created</h2>
            <p>
              <strong>{completedAccount?.username}</strong> was created successfully. Log in to manage your account and activate a plan when you are ready to connect.
            </p>
            <div className="signup-next-note">
              <ShieldIcon />
              <p><strong>Your login is reserved</strong><span>Your account is tied to your selected hostel&apos;s network.</span></p>
            </div>
            <a className="signup-submit signup-login-link" href="/">Continue to login</a>
          </section>
        </div>
      </main>
    )
  }

  return (
    <main className="signup-page">
      <div className="signup-container">
        <SignupHeader />

        <section className="signup-card" aria-labelledby="signup-title">
          <div className="signup-card-header">
            <span className="signup-step">Step 1 of 2</span>
            <h2 id="signup-title">Account details</h2>
            <p>We will verify your phone number before creating your account.</p>
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
              <label htmlFor="signup-phone">Phone number</label>
              <input
                autoComplete="tel"
                className={errors.phoneNumber ? 'signup-input invalid' : 'signup-input'}
                id="signup-phone"
                inputMode="tel"
                maxLength={18}
                name="phoneNumber"
                placeholder="024 123 4567"
                type="tel"
                value={form.phoneNumber}
                onChange={updateField}
                aria-describedby="signup-phone-help signup-phone-error"
                aria-invalid={Boolean(errors.phoneNumber)}
              />
              <span className="signup-field-help" id="signup-phone-help">We will send your account verification code to this number.</span>
              <FieldError id="signup-phone-error" message={errors.phoneNumber} />
            </div>

            <div className="signup-field">
              <label htmlFor="signup-username">Username</label>
              <input
                autoCapitalize="none"
                autoComplete="off"
                className={errors.username ? 'signup-input invalid' : 'signup-input'}
                id="signup-username"
                maxLength={64}
                name="username"
                placeholder="e.g. amab123"
                spellCheck="false"
                type="text"
                value={form.username}
                onChange={updateField}
                aria-describedby="signup-username-help signup-username-error"
                aria-invalid={Boolean(errors.username)}
              />
              <span className="signup-field-help" id="signup-username-help">This will be your permanent WiFi username.</span>
              {usernameAvailability.phase === 'checking' && (
                <span className="username-availability checking" role="status">Checking availability...</span>
              )}
              {usernameAvailability.phase === 'available' && routerReadiness.phase !== 'username-taken' && (
                <span className="username-availability available" role="status">Username is available.</span>
              )}
              {usernameAvailability.phase === 'unavailable' && (
                <div className="username-unavailable" role="status">
                  <span className="username-availability unavailable">Username is already taken.</span>
                  {usernameAvailability.suggestions.length > 0 && (
                    <div className="username-suggestions">
                      <span>Try:</span>
                      {usernameAvailability.suggestions.map((suggestion) => (
                        <button key={suggestion} type="button" onClick={() => chooseSuggestedUsername(suggestion)}>
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {usernameAvailability.phase === 'error' && (
                <span className="username-availability error" role="status">Availability could not be checked. It will be checked again when you continue.</span>
              )}
              {routerReadiness.phase === 'username-taken' && (
                <span className="username-availability unavailable" role="status">
                  That username is already in use for this hostel. Choose another username.
                </span>
              )}
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
                Your account will be tied to this hostel&apos;s network.
              </span>
              {routersPhase === 'error' && (
                <span className="signup-field-error">Hostels could not be loaded. Please try again or contact help and support.</span>
              )}
              {routersPhase === 'loaded' && routers.length === 0 && (
                <span className="signup-field-error">No hostels are currently available.</span>
              )}
              {routerReadiness.phase === 'checking' && (
                <span className="username-availability checking" role="status">Checking hostel availability...</span>
              )}
              {routerReadiness.phase === 'ready' && (
                <span className="username-availability available" role="status">Hostel is available for signup.</span>
              )}
              {routerReadiness.phase === 'unavailable' && (
                <span className="signup-field-error" role="status">
                  Signup is currently unavailable. Please contact help and support.
                </span>
              )}
              <FieldError id="signup-hostel-error" message={errors.routerId} />
            </div>

            <div className="signup-field">
              <label htmlFor="signup-pin">Create 6-digit PIN</label>
              <div className="signup-password-wrap">
                <input
                  autoComplete="off"
                  className={`${errors.pin ? 'signup-input invalid' : 'signup-input'} pin-input${showPin ? '' : ' pin-masked'}`}
                  id="signup-pin"
                  inputMode="numeric"
                  maxLength={6}
                  name="pin"
                  placeholder="6 digits"
                  type="text"
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
                  autoComplete="off"
                  className={`${errors.confirmPin ? 'signup-input invalid' : 'signup-input'} pin-input${showConfirmPin ? '' : ' pin-masked'}`}
                  id="signup-confirm-pin"
                  inputMode="numeric"
                  maxLength={6}
                  name="confirmPin"
                  placeholder="Enter PIN again"
                  type="text"
                  value={form.confirmPin}
                  onChange={updateField}
                  aria-describedby={errors.confirmPin ? 'signup-confirm-pin-error' : undefined}
                  aria-invalid={Boolean(errors.confirmPin)}
                />
                <button type="button" onClick={() => setShowConfirmPin((shown) => !shown)}>{showConfirmPin ? 'Hide' : 'Show'}</button>
              </div>
              <FieldError id="signup-confirm-pin-error" message={errors.confirmPin} />
            </div>

            <div className="signup-field signup-field-wide terms-field">
              <label className="auth-checkbox" htmlFor="accepted-terms">
                <input
                  checked={form.acceptedTerms}
                  id="accepted-terms"
                  name="acceptedTerms"
                  type="checkbox"
                  onChange={updateField}
                  aria-describedby={errors.acceptedTerms ? 'accepted-terms-error' : undefined}
                  aria-invalid={Boolean(errors.acceptedTerms)}
                />
                <span>I agree to the <a href="/terms" target="_blank" rel="noreferrer">Terms and Conditions</a> and acknowledge the <a href="/privacy" target="_blank" rel="noreferrer">Privacy Notice</a>.</span>
              </label>
              <FieldError id="accepted-terms-error" message={errors.acceptedTerms} />
            </div>

            {apiError && <div className="otp-api-error signup-field-wide" role="alert">{apiError}</div>}

            <button
              className="signup-submit signup-field-wide"
              disabled={
                busy ||
                routersPhase !== 'loaded' ||
                routers.length === 0 ||
                usernameAvailability.phase === 'unavailable' ||
                routerReadiness.phase !== 'ready'
              }
              type="submit"
            >
              {busy ? 'Sending verification code...' : 'Continue to phone verification'}
            </button>
          </form>

          <p className="signup-footer-link">Already have an account? <a href="/">Log in</a></p>
          <p className="auth-legal-links"><a href="/terms">Terms</a><span>&middot;</span><a href="/privacy">Privacy</a></p>
        </section>
      </div>
    </main>
  )
}
