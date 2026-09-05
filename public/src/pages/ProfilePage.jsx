import { useEffect, useState } from 'react'

import AccountHeader from '../components/AccountHeader'
import { AccountIcon, GlobeIcon, ShieldIcon } from '../components/Icons'
import { AccountApiError, getAccount, logout } from '../services/accountApi'

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

        <section className="profile-signout-card">
          <div>
            <h2>Log out of your account</h2>
            <p>You will need your username and PIN to log in again.</p>
          </div>
          <button type="button" onClick={signOut} disabled={loggingOut}>
            {loggingOut ? 'Logging out...' : 'Log out'}
          </button>
        </section>
      </div>
    </main>
  )
}
