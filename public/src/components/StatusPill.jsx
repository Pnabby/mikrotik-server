export default function StatusPill({ children, className = '' }) {
  return <span className={`status-pill ${className}`}>{children}</span>
}
