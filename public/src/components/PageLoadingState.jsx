import AccountHeader from './AccountHeader'

export default function PageLoadingState({ activePage, message, title }) {
  return (
    <>
    {activePage && <AccountHeader activePage={activePage} activeSection={activePage === 'plans' ? 'plans' : 'overview'} />}
    <main
      aria-busy="true"
      aria-live="polite"
      className="account-page account-state-page"
      role="status"
    >
      <div className="loading-status-card">
        <div className="account-loader" aria-hidden="true" />
        <h1>{title}</h1>
        {message && <p>{message}</p>}
        <div className="loading-skeleton" aria-hidden="true"><span /><span /><span /></div>
      </div>
    </main>
    </>
  )
}
