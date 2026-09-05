import { AccountIcon, WifiIcon } from './Icons'

export default function AccountHeader({ account, activePage = 'account', activeSection = 'overview' }) {
  const initial = account.username.slice(0, 1).toUpperCase()
  const onAccountPage = activePage === 'account'
  const sections = [
    { id: 'overview', label: 'Overview' },
    { id: 'plans', label: 'Plans' },
    { id: 'purchases', label: 'Purchases' },
  ]

  return (
    <header className="account-topbar">
      <a className="account-brand" href="/account#overview" aria-label="Flint WiFi dashboard">
        <span><WifiIcon /></span>
        <strong>Flint WiFi</strong>
      </a>

      <nav className="account-nav" aria-label="Account navigation">
        {sections.map((section) => {
          const isActive = onAccountPage && activeSection === section.id
          return (
            <a
              aria-current={isActive ? 'location' : undefined}
              className={isActive ? 'active' : ''}
              href={onAccountPage ? `#${section.id}` : `/account#${section.id}`}
              key={section.id}
            >
              {section.label}
            </a>
          )
        })}
      </nav>

      <a
        className={`account-profile-link${activePage === 'profile' ? ' active' : ''}`}
        href="/profile"
        aria-label="Open profile"
      >
        <span className="account-avatar" aria-hidden="true">{initial}</span>
        <span className="account-profile-copy">
          <strong>{account.username}</strong>
          <small>Profile</small>
        </span>
        <AccountIcon />
      </a>
    </header>
  )
}
