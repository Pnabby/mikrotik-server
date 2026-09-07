import { useEffect, useState } from 'react'

import AccountHeader from '../components/AccountHeader'
import { AccountIcon, GlobeIcon, ShieldIcon } from '../components/Icons'
import { AccountApiError, changePin, deleteAccount, getAccount, logout } from '../services/accountApi'

function friendlyStatus(status) {
  const labels = {
    active: 'Active',
    inactive: 'Ready for a plan',
    suspended: 'Suspended',
    closed: 'Closed',
  }
  return labels[status] || 'Unavailable'
}

export default function ProfilePage() {
  const [account, setAccount] = useState(null)
  const [phase, setPhase] = useState('loading')
  const [loggingOut, setLoggingOut] = useState(false)
  const [showDelete, setShowDelete] = useState(false)
  const [deletePin, setDeletePin] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [pinForm, setPinForm] = useState({ oldPin: '', newPin: '', confirmation: '' })
  const [changingPin, setChangingPin] = useState(false)
  const [pinError, setPinError] = useState('')
  const [pinSuccess, setPinSuccess] = useState('')

  useEffect(() => {
    document.title = 'Profile | FLINT WiFi'
    let active = true
    getAccount()
      .then((result) => {
        if (!active) return
        setAccount(result)
        setPhase('ready')
      })
      .catch((error) => {
        if (!active) return
        if (error instanceof AccountApiError && error.status === 401) {
          window.location.replace('/')
          return
        }
        setPhase('error')
      })
    return () => {
      active = false
    }
  }, [])

  async function signOut() {
    if (loggingOut) return
    setLoggingOut(true)
    try {
      await logout()
    } finally {
      window.location.replace('/')
    }
  }

  async function permanentlyDelete(event) {
    event.preventDefault()
    if (!/^[0-9]{6}$/.test(deletePin) || deleting) {
      setDeleteError('Enter your 6-digit PIN to confirm deletion.')
      return
    }
    setDeleting(true)
    setDeleteError('')
    try {
      await deleteAccount(deletePin)
      window.location.replace('/')
    } catch (error) {
      if (error instanceof AccountApiError && error.status === 401) {
        setDeleteError('The PIN is incorrect. Your account was not deleted.')
      } else if (error instanceof AccountApiError && [502, 503].includes(error.status)) {
        setDeleteError('The network is temporarily unavailable. Nothing was deleted; please try again.')
      } else {
        setDeleteError('Your account could not be completely deleted. Please try again or contact support.')
      }
    } finally {
      setDeleting(false)
    }
  }

  function updatePin(event) {
    const { name, value } = event.target
    setPinForm((current) => ({ ...current, [name]: value.replace(/\D/g, '').slice(0, 6) }))
    setPinError('')
    setPinSuccess('')
  }

  async function submitPinChange(event) {
    event.preventDefault()
    if (!/^[0-9]{6}$/.test(pinForm.oldPin) || !/^[0-9]{6}$/.test(pinForm.newPin)) {
      setPinError('Enter your current PIN and a new 6-digit PIN.')
      return
    }
    if (pinForm.newPin !== pinForm.confirmation) {
      setPinError('The new PINs do not match.')
      return
    }
    if (pinForm.newPin === pinForm.oldPin) {
      setPinError('Choose a new PIN that is different from your current PIN.')
      return
    }
    setChangingPin(true)
    setPinError('')
    setPinSuccess('')
    try {
      await changePin(pinForm.oldPin, pinForm.newPin, pinForm.confirmation)
      setPinForm({ oldPin: '', newPin: '', confirmation: '' })
      setPinSuccess('Your PIN was changed successfully on Flint and your hostel router.')
    } catch (error) {
      if (error instanceof AccountApiError && error.status === 401) {
        setPinError('Your current PIN is incorrect.')
      } else if (error instanceof AccountApiError && [502, 503].includes(error.status)) {
        setPinError('Your hostel router is unavailable. Your PIN was not changed.')
      } else {
        setPinError('Your PIN could not be changed. Please try again.')
      }
    } finally {
      setChangingPin(false)
    }
  }

  if (phase === 'loading') {
    return (
      <main className="account-page account-state-page" aria-busy="true">
        <div className="account-loader" />
        <h1>Loading your profile</h1>
      </main>
    )
  }
  if (phase === 'error' || !account) {
    return (
      <main className="account-page account-state-page">
        <ShieldIcon />
        <h1>Your profile could not be loaded</h1>
        <p>Please try again or contact help and support.</p>
        <button type="button" onClick={() => window.location.reload()}>Try again</button>
      </main>
    )
  }

  return (
    <main className="account-page">
      <AccountHeader account={account} activePage="profile" />
      <div className="account-shell profile-shell">
        <a className="profile-back-link" href="/account">← Back to overview</a>
        <section className="profile-heading">
          <span className="account-eyebrow">Profile</span>
          <h1>Account details</h1>
          <p>Review the information connected to your Flint WiFi account.</p>
        </section>

        <div className="profile-layout">
          <section className="profile-card">
            <div className="profile-card-heading">
              <span><AccountIcon /></span>
              <div>
                <h2>{account.username}</h2>
                <p>{account.email}</p>
              </div>
            </div>
            <dl className="profile-details">
              <div><dt>Username</dt><dd>{account.username}</dd></div>
              <div><dt>Email address</dt><dd>{account.email}</dd></div>
              <div><dt>Hostel</dt><dd>{account.hostel_name}</dd></div>
              <div><dt>Account status</dt><dd><span className={`profile-status status-${account.account_status}`}>{friendlyStatus(account.account_status)}</span></dd></div>
            </dl>
          </section>

          <aside className="profile-side-card">
            <span className="profile-side-icon"><GlobeIcon /></span>
            <h2>Your hostel network</h2>
            <p>Your account is tied to {account.hostel_name}. Contact help and support if this is incorrect.</p>
          </aside>
        </div>

        <section className="profile-pin-card">
          <div>
            <h2>Change password (PIN)</h2>
            <p>Enter your current PIN, then enter your new 6-digit PIN twice. We will verify your hostel router before changing it.</p>
          </div>
          <form className="profile-pin-form" noValidate onSubmit={submitPinChange}>
            <label htmlFor="current-pin">Current PIN</label>
            <input autoComplete="current-password" id="current-pin" inputMode="numeric" maxLength="6" name="oldPin" placeholder="Current 6-digit PIN" type="password" value={pinForm.oldPin} onChange={updatePin} />
            <div className="profile-pin-columns">
              <div><label htmlFor="new-pin">New PIN</label><input autoComplete="new-password" id="new-pin" inputMode="numeric" maxLength="6" name="newPin" placeholder="New 6-digit PIN" type="password" value={pinForm.newPin} onChange={updatePin} /></div>
              <div><label htmlFor="confirm-new-pin">Confirm new PIN</label><input autoComplete="new-password" id="confirm-new-pin" inputMode="numeric" maxLength="6" name="confirmation" placeholder="Repeat new PIN" type="password" value={pinForm.confirmation} onChange={updatePin} /></div>
            </div>
            {pinError && <p className="profile-pin-message error" role="alert">{pinError}</p>}
            {pinSuccess && <p className="profile-pin-message success" role="status">{pinSuccess}</p>}
            <button disabled={changingPin} type="submit">{changingPin ? 'Checking router...' : 'Change PIN'}</button>
          </form>
        </section>

        <section className="profile-signout-card">
          <div>
            <h2>Log out of your account</h2>
            <p>You will need your username and PIN to log in again.</p>
          </div>
          <button type="button" onClick={signOut} disabled={loggingOut}>
            {loggingOut ? 'Logging out...' : 'Log out'}
          </button>
        </section>

        <section className="profile-delete-card">
          <div>
            <h2>Delete account permanently</h2>
            <p>This removes your Flint account, plan history, sessions, hotspot user, and remembered hotspot cookies. This cannot be undone.</p>
          </div>
          {!showDelete ? (
            <button className="delete-account-open" type="button" onClick={() => setShowDelete(true)}>Delete account</button>
          ) : (
            <form className="delete-account-form" onSubmit={permanentlyDelete}>
              <label htmlFor="delete-account-pin">Enter your PIN to confirm</label>
              <input
                autoComplete="off"
                id="delete-account-pin"
                inputMode="numeric"
                maxLength={6}
                placeholder="6-digit PIN"
                type="password"
                value={deletePin}
                onChange={(event) => {
                  setDeletePin(event.target.value.replace(/\D/g, ''))
                  setDeleteError('')
                }}
              />
              {deleteError && <p className="delete-account-error" role="alert">{deleteError}</p>}
              <div>
                <button type="button" onClick={() => { setShowDelete(false); setDeletePin(''); setDeleteError('') }}>Cancel</button>
                <button className="confirm-delete" disabled={deleting} type="submit">{deleting ? 'Deleting...' : 'Delete permanently'}</button>
              </div>
            </form>
          )}
        </section>

        <p className="profile-legal-links"><a href="/terms">Terms</a><span>&middot;</span><a href="/privacy">Privacy</a></p>
      </div>
    </main>
  )
}
