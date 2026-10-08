import { useEffect, useRef, useState } from 'react'

import { applyTheme, initialTheme, savePreference } from '../theme'
import { getNotifications } from '../services/adminApi'

const PAGES = [
  ['dashboard', 'Dashboard', 'grid', 'overview'],
  ['hostels', 'Hostels', 'building', 'locations buildings'],
  ['profiles', 'Profile catalogue', 'tag', 'plans packages'],
  ['customers', 'Customers & devices', 'users', 'users accounts'],
  ['network', 'Network & usage', 'network', 'wifi routers connections traffic'],
  ['wireguard', 'WireGuard & VPN', 'shield', 'peers back to home bth qr restart router'],
  ['transactions', 'Transactions', 'receipt', 'payments receipts sales'],
  ['analysis', 'Revenue & analysis', 'activity', 'reports charts forecasts'],
  ['support', 'Help & support', 'settings', 'contact phone whatsapp'],
  ['issues', 'Issues & complaints', 'alert', 'support complaints notifications room reply'],
]

function HeaderIcon({ name, Icon }) {
  const paths = {
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5" /></>,
    moon: <path d="M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13Z" />,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
  }
  return paths[name] ? <svg className="header-icon" aria-hidden="true" viewBox="0 0 24 24">{paths[name]}</svg> : <Icon name={name} />
}

export default function AdminHeader({ admin, view, Icon, onNavigate, onRequestLogout, signingOut, mobileSidebarOpen, onToggleSidebar, onSessionExpired }) {
  const [theme, setTheme] = useState(initialTheme)
  const [popover, setPopover] = useState('')
  const [query, setQuery] = useState('')
  const [notifications, setNotifications] = useState(null)
  const [notificationError, setNotificationError] = useState('')
  const header = useRef(null)
  const search = useRef(null)
  const accountButton = useRef(null)
  const notificationButton = useRef(null)
  const roleLabel = { admin: 'Administrator', operator: 'Operator', viewer: 'Viewer' }[admin.role] || admin.role
  const results = PAGES.filter(([, label, , aliases]) => `${label} ${aliases}`.toLowerCase().includes(query.trim().toLowerCase()))

  useEffect(() => {
    let active = true
    let running = false
    async function refresh() {
      if (running) return
      running = true
      try {
        const result = await getNotifications()
        if (active) { setNotifications(result); setNotificationError('') }
      } catch (err) {
        if (active) {
          if (err.status === 401) onSessionExpired()
          else setNotificationError('Notifications could not be refreshed.')
        }
      } finally { running = false }
    }
    refresh()
    const timer = window.setInterval(refresh, 15000)
    window.addEventListener('vlad:issues-updated', refresh)
    window.addEventListener('focus', refresh)
    return () => { active = false; window.clearInterval(timer); window.removeEventListener('vlad:issues-updated', refresh); window.removeEventListener('focus', refresh) }
  }, [onSessionExpired])

  useEffect(() => { applyTheme(theme); savePreference('vlad-wifi-theme', theme) }, [theme])
  useEffect(() => { setPopover(''); setQuery('') }, [view])
  useEffect(() => {
    function outside(event) { if (!header.current?.contains(event.target)) setPopover('') }
    function escape(event) {
      if (event.key !== 'Escape' || !popover) return
      if (popover === 'search') search.current?.focus()
      else if (popover === 'profile') accountButton.current?.focus()
      else notificationButton.current?.focus()
      setPopover('')
    }
    document.addEventListener('pointerdown', outside)
    window.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', outside); window.removeEventListener('keydown', escape) }
  }, [popover])

  function navigate(next) { setPopover(''); setQuery(''); onNavigate(next) }
  function searchKeyboard(event) {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
    if (event.target === search.current && ['Home', 'End'].includes(event.key)) return
    const options = Array.from(header.current.querySelectorAll('[role="option"]'))
    if (!options.length) return
    event.preventDefault()
    const index = options.indexOf(document.activeElement)
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1 : index < 0 ? event.key === 'ArrowUp' ? options.length - 1 : 0 : (index + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length
    options[next].focus()
  }

  return <header className="dashboard-topbar admin-topbar" ref={header}>
    <div className="dashboard-topbar-start">
      <button className="dashboard-menu-button" type="button" aria-label={mobileSidebarOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={mobileSidebarOpen} onClick={onToggleSidebar}><Icon name="menu" /></button>
      <form className="header-search-form" role="search" onKeyDown={searchKeyboard} onSubmit={(event) => { event.preventDefault(); if (document.activeElement === search.current && results[0]) navigate(results[0][0]) }}>
        <div className="header-search"><Icon name="search" /><input ref={search} role="combobox" aria-label="Search admin pages" aria-autocomplete="list" aria-haspopup="listbox" aria-controls="admin-search-results" aria-expanded={popover === 'search'} placeholder="Search users, devices, payments" type="search" value={query} onFocus={() => setPopover('search')} onChange={(event) => { setQuery(event.target.value); setPopover('search') }} /></div>
        {popover === 'search' && <div className="header-popover search-results" id="admin-search-results" role="listbox" aria-label="Admin pages">
          <small role="presentation">Go to a workspace</small>
          {results.map(([key, label, icon]) => <button role="option" aria-selected="false" type="button" key={key} onClick={() => navigate(key)}><Icon name={icon} /><span>{label}</span><Icon name="chevron" /></button>)}
          {!results.length && <div role="option" aria-selected="false" tabIndex={0}>No matching pages. Open Customers &amp; devices or Transactions to search records.</div>}
        </div>}
      </form>
    </div>
    <div className="header-tools">
      <button className="header-icon-button" type="button" aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'} title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'} onClick={() => setTheme((value) => value === 'dark' ? 'light' : 'dark')}><HeaderIcon name={theme === 'dark' ? 'sun' : 'moon'} Icon={Icon} /></button>
      <div className="notification-menu">
        <button ref={notificationButton} className="header-icon-button notification-trigger" type="button" aria-label={`Notifications${notifications ? `: ${notifications.count} issues awaiting attention` : ''}`} aria-expanded={popover === 'notifications'} aria-controls="session-notifications" onClick={() => setPopover((value) => value === 'notifications' ? '' : 'notifications')}><HeaderIcon name="bell" Icon={Icon} />{notifications && <span className="notification-count" aria-hidden="true">{notifications.count > 99 ? '99+' : notifications.count}</span>}</button>
        {popover === 'notifications' && <div className="header-popover notification-popover" id="session-notifications"><strong>Notifications {notifications && `(${notifications.count})`}</strong>
          {notificationError && <p className="notification-error" role="alert">{notificationError}</p>}
          {!notifications && !notificationError && <p>Loading notifications…</p>}
          {notifications?.count === 0 && <div><span className="header-notification-icon"><Icon name="check" /></span><p>No issues awaiting attention.</p></div>}
          {notifications?.items.map((issue) => <button className="issue-notification" type="button" key={issue.id} onClick={() => navigate('issues')}><strong>{issue.subject}</strong><small>{issue.hostel_name} · {issue.username}{issue.room_number ? ` · Room ${issue.room_number}` : ''}</small></button>)}
          <button type="button" onClick={() => navigate('issues')}>View all issues</button>
        </div>}
      </div>
      <div className="dashboard-admin-menu">
        <button ref={accountButton} className="admin-profile-trigger" type="button" aria-label="Open account menu" aria-haspopup="menu" aria-expanded={popover === 'profile'} onClick={() => setPopover((value) => value === 'profile' ? '' : 'profile')}><span className="admin-profile-copy"><strong>{admin.username}</strong><small>{roleLabel}</small></span><span className="admin-avatar">{admin.username.slice(0, 1).toUpperCase()}</span></button>
        {popover === 'profile' && <div className="admin-profile-dropdown" role="menu"><div className="admin-profile-dropdown-heading"><span className="admin-avatar">{admin.username.slice(0, 1).toUpperCase()}</span><div><strong>{admin.username}</strong><small>{roleLabel}</small></div></div><div className="admin-profile-session"><Icon name="check" /><span><strong>Secure session</strong><small>Protected admin access</small></span></div><button role="menuitem" disabled={signingOut} type="button" onClick={() => { setPopover(''); onRequestLogout() }}><Icon name="logout" /><span>Log out</span></button></div>}
      </div>
    </div>
  </header>
}
