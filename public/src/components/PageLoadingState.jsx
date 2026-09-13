export default function PageLoadingState({ message, title }) {
  return (
    <main
      aria-busy="true"
      aria-live="polite"
      className="account-page account-state-page"
      role="status"
    >
      <div className="account-loader" aria-hidden="true" />
      <h1>{title}</h1>
      {message && <p>{message}</p>}
    </main>
  )
}
