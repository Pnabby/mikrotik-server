import { useEffect, useState } from 'react'

import AccountHeader from '../components/AccountHeader'
import { AccountIcon, GlobeIcon, ShieldIcon, WarningIcon } from '../components/Icons'
import PageLoadingState from '../components/PageLoadingState'
import {
  AccountApiError,
  changePin,
  deleteAccount,
  getAccount,
  listAvailableHostels,
  logout,
  transferHostel,
} from '../services/accountApi'

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
  const [hostels, setHostels] = useState([])
  const [hostelsPhase, setHostelsPhase] = useState('loading')
  const [showTransfer, setShowTransfer] = useState(false)
  const [transferForm, setTransferForm] = useState({ destinationRouterId: '', pin: '' })
  const [transferring, setTransferring] = useState(false)
  const [transferError, setTransferError] = useState('')
  const [transferSuccess, setTransferSuccess] = useState('')

  useEffect(() => {
    document.title = 'Profile | Vlad WiFi'
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
    listAvailableHostels().then((items) => {
      if (!active) return
      setHostels(items)
      setHostelsPhase('ready')
    }).catch(() => {
      if (active) setHostelsPhase('error')
    })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!showDelete && !showTransfer) return undefined

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    function closeOnEscape(event) {
      if (event.key !== 'Escape' || deleting || transferring) return
      if (showDelete) closeDeleteModal()
      if (showTransfer) closeTransferModal()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [showDelete, showTransfer, deleting, transferring])

  function closeDeleteModal() {
    if (deleting) return
    setShowDelete(false)
    setDeletePin('')
    setDeleteError('')
  }

  function closeTransferModal() {
    if (transferring) return
    setShowTransfer(false)
    setTransferForm({ destinationRouterId: '', pin: '' })
    setTransferError('')
  }

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
      setPinSuccess('Your PIN was changed successfully on Vlad WiFi and your hostel router.')
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

  async function submitHostelTransfer(event) {
    event.preventDefault()
    if (transferring) return
    if (!transferForm.destinationRouterId) {
      setTransferError('Select the hostel you are moving to.')
      return
    }
    if (!/^[0-9]{6}$/.test(transferForm.pin)) {
      setTransferError('Enter your 6-digit PIN to confirm the hostel change.')
      return
    }
    setTransferring(true)
    setTransferError('')
    setTransferSuccess('')
    try {
      const result = await transferHostel(transferForm.destinationRouterId, transferForm.pin)
      setAccount((current) => ({
        ...current,
        router_id: result.router_id,
        hostel_name: result.hostel_name,
      }))
      setTransferForm({ destinationRouterId: '', pin: '' })
      setShowTransfer(false)
      setTransferSuccess(`Your account is now registered at ${result.hostel_name}. Sign in to that hostel's WiFi again.`)
    } catch (error) {
      if (error instanceof AccountApiError && error.status === 401) {
        setTransferError('The PIN is incorrect. Your hostel was not changed.')
      } else if (error instanceof AccountApiError && error.status === 409) {
        const reasons = {
          hostel_already_selected: 'Your account is already registered at this hostel.',
          hostel_activation_pending: 'Your WiFi plan activation is still pending. Open Purchases and retry activation before moving hostels.',
          hostel_transfer_in_progress: 'An account update or hostel move is already running or awaiting recovery. Refresh your profile and try again shortly. Contact support if it stays pending.',
          hostel_username_conflict: 'Your username already exists there. Please raise an issue so an admin can help.',
          hostel_source_user_missing: 'Your network account needs an admin repair. Please raise an issue.',
          hostel_profile_missing: 'Your plan is missing at that hostel. Ask an admin to match the hostel plans in the Profile catalogue.',
          hostel_profile_mismatch: 'The hostels have different speed, device, or timeout settings for your plan. Ask an admin to match them in the Profile catalogue.',
        }
        setTransferError(reasons[error.code] || 'This account cannot be moved yet. Please raise an issue so an admin can help.')
      } else if (error instanceof AccountApiError && error.code === 'hostel_transfer_unconfirmed') {
        setTransferError('The routers could not confirm the move. Please raise an issue so an admin can check your account before you retry.')
      } else if (error instanceof AccountApiError && error.code && (
        error.code.startsWith('hostel_source_router_') || error.code.startsWith('hostel_destination_router_') ||
        ['hostel_both_routers_not_ready', 'hostel_transfer_storage_unavailable', 'hostel_transfer_not_configured', 'router_not_configured', 'router_request_failed'].includes(error.code)
      )) {
        setTransferError(error.detail || 'The move could not be started. Please contact support.')
      } else if (error instanceof AccountApiError && [502, 503].includes(error.status)) {
        setTransferError('The server could not complete the move. Please raise an issue so an admin can check the cause.')
      } else {
        setTransferError('The hostel change could not be completed. Please try again or contact support.')
      }
    } finally {
      setTransferring(false)
    }
  }

  if (phase === 'loading' || hostelsPhase === 'loading') {
    return (
      <PageLoadingState
        title="Loading your profile"
        message="Fetching your account and hostel details."
      />
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
          <p>Review the information connected to your Vlad WiFi account.</p>
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
              <div>
                <dt>Phone number</dt>
                <dd className="profile-phone-value">
                  <span>{account.phone_number || 'Not added'}</span>
                  {account.phone_verified
                    ? <small className="profile-phone-verified">Verified</small>
                    : <a href="/verify-phone">Add and verify</a>}
                </dd>
              </div>
              <div><dt>Hostel</dt><dd>{account.hostel_name}</dd></div>
              <div><dt>Account status</dt><dd><span className={`profile-status status-${account.account_status}`}>{friendlyStatus(account.account_status)}</span></dd></div>
            </dl>
          </section>

          <aside className="profile-side-card">
            <span className="profile-side-icon"><GlobeIcon /></span>
            <h2>Your hostel network</h2>
            <p>Your account is currently on {account.hostel_name}. If you move, transfer it to your new hostel here.</p>
            {transferSuccess && <p className="hostel-transfer-message success" role="status">{transferSuccess}</p>}
            <button className="hostel-transfer-open" disabled={hostels.filter((hostel) => hostel.router_id !== account.router_id).length === 0} type="button" onClick={() => { setShowTransfer(true); setTransferError(''); setTransferSuccess('') }}>Change hostel</button>
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
            <p>This removes your Vlad WiFi account, plan history, sessions, hotspot user, and remembered hotspot cookies. This cannot be undone.</p>
          </div>
          <button className="delete-account-open" type="button" onClick={() => setShowDelete(true)}>Delete account</button>
        </section>

        <p className="profile-legal-links"><a href="/terms">Terms</a><span>&middot;</span><a href="/privacy">Privacy</a></p>
      </div>

      {showTransfer && (
        <div className="portal-modal-backdrop" role="presentation" onMouseDown={closeTransferModal}>
          <section className="portal-modal profile-action-modal" role="dialog" aria-modal="true" aria-labelledby="transfer-hostel-title" onMouseDown={(event) => event.stopPropagation()}>
            <span className="portal-modal-icon profile-transfer-modal-icon"><GlobeIcon /></span>
            <h2 id="transfer-hostel-title">Move to a new hostel?</h2>
            <p>Your account will be moved from <strong>{account.hostel_name}</strong>. All active WiFi sessions and remembered logins will end first.</p>
            <form className="profile-modal-form" noValidate onSubmit={submitHostelTransfer}>
              <label htmlFor="destination-hostel"><span>New hostel</span>
                <select autoFocus disabled={transferring} id="destination-hostel" value={transferForm.destinationRouterId} onChange={(event) => { setTransferForm((current) => ({ ...current, destinationRouterId: event.target.value })); setTransferError('') }}>
                  <option value="">Select your new hostel</option>
                  {hostels.filter((hostel) => hostel.router_id !== account.router_id).map((hostel) => <option key={hostel.router_id} value={hostel.router_id}>{hostel.name}</option>)}
                </select>
              </label>
              <label htmlFor="hostel-transfer-pin"><span>Enter your PIN to confirm</span>
                <input autoComplete="current-password" disabled={transferring} id="hostel-transfer-pin" inputMode="numeric" maxLength={6} placeholder="6-digit PIN" type="password" value={transferForm.pin} onChange={(event) => { setTransferForm((current) => ({ ...current, pin: event.target.value.replace(/\D/g, '').slice(0, 6) })); setTransferError('') }} />
              </label>
              <small>Any data already used is deducted before your remaining allowance moves to the new hostel.</small>
              {transferring ? (
                <aside className="transfer-progress" role="status" aria-live="polite">
                  <span className="transfer-spinner" aria-hidden="true" />
                  <div><strong>Moving your account</strong><small>This may take 30 seconds or more. Please keep this page open.</small></div>
                </aside>
              ) : <small>The move may take 30 seconds or more.</small>}
              {transferError && <p className="portal-modal-error" role="alert">{transferError} <a href="/issues">Raise an issue</a></p>}
              <div className="portal-modal-actions">
                <button disabled={transferring} type="button" onClick={closeTransferModal}>Cancel</button>
                <button className="confirm" aria-busy={transferring} disabled={transferring} type="submit">{transferring ? 'Moving account...' : 'Confirm hostel move'}</button>
              </div>
            </form>
          </section>
        </div>
      )}

      {showDelete && (
        <div className="portal-modal-backdrop" role="presentation" onMouseDown={closeDeleteModal}>
          <section className="portal-modal profile-action-modal" role="dialog" aria-modal="true" aria-labelledby="delete-account-title" onMouseDown={(event) => event.stopPropagation()}>
            <span className="portal-modal-icon"><WarningIcon /></span>
            <h2 id="delete-account-title">Delete your account permanently?</h2>
            <p>Your account, plan history, sessions, hotspot user, and remembered cookies will be removed. <strong>This cannot be undone.</strong></p>
            <form className="profile-modal-form" noValidate onSubmit={permanentlyDelete}>
              <label htmlFor="delete-account-pin"><span>Enter your PIN to confirm</span>
                <input autoFocus autoComplete="off" id="delete-account-pin" inputMode="numeric" maxLength={6} placeholder="6-digit PIN" type="password" value={deletePin} onChange={(event) => { setDeletePin(event.target.value.replace(/\D/g, '')); setDeleteError('') }} />
              </label>
              {deleteError && <p className="portal-modal-error" role="alert">{deleteError}</p>}
              <div className="portal-modal-actions">
                <button disabled={deleting} type="button" onClick={closeDeleteModal}>Cancel</button>
                <button className="danger" disabled={deleting} type="submit">{deleting ? 'Deleting...' : 'Delete permanently'}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </main>
  )
}
