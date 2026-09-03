import { WifiIcon } from './Icons'

export default function Header({ phase, username }) {
  let dotClass = 'idle'
  let label = 'No user'
  let chipClass = 'user-chip inactive'
  if (phase === 'loading') {
    dotClass = 'loading'
    label = username
    chipClass = 'user-chip'
  } else if (phase === 'loaded') {
    dotClass = 'active'
    label = username
    chipClass = 'user-chip'
  } else if (phase === 'error') {
    dotClass = 'error'
    label = username || 'Error'
    chipClass = 'user-chip'
  }

  return (
    <div className="header">
      <div className="logo-icon"><WifiIcon /></div>
      <span className="logo-text">FLINT <span>WiFi</span></span>
      <span className={chipClass} id="hero-badge" title={label}>
        <span className={`status-dot ${dotClass}`} />
        {label}
      </span>
    </div>
  )
}
