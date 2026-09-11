import { AccountIcon, WifiIcon } from './Icons'

export default function AccountHeader({ activePage = 'account', activeSection = 'overview' }) {
  const onAccountPage = activePage === 'account'
  const sections = [
    { id: 'overview', label: 'Overview' },
    { id: 'plans', label: 'Plans' },
    { id: 'purchases', label: 'Purchases' },
  ]

  return (
    <header className="account-topbar">
      <a className="account-brand" href="/account#overview" aria-label="Vlad WiFi dashboard">
        <span><WifiIcon /></span>
        <strong>Vlad WiFi</strong>
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
        <AccountIcon />
      </a>
    </header>
  )
}
