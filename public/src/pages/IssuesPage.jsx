import { useEffect, useState } from 'react'

import AccountHeader from '../components/AccountHeader'
import PageLoadingState from '../components/PageLoadingState'
import { ChatIcon, CheckIcon, ClockIcon, GlobeIcon, SendIcon, ShieldIcon, WarningIcon } from '../components/Icons'
import { AccountApiError, createIssue, getAccount, listIssues } from '../services/accountApi'
import '../styles/issues.css'

function IssueStatus({ status }) {
  return <span className={`issue-status ${status}`}>
    {status === 'attended' ? <CheckIcon /> : <ClockIcon />}
    {status === 'attended' ? 'Attended to' : 'Awaiting attention'}
  </span>
}

function IssueHistoryCard({ issue }) {
  return <article className="issue-card issue-history-card">
    <div className="issue-title"><h3>{issue.subject}</h3><IssueStatus status={issue.status} /></div>
    <div className="issue-meta">
      <span><GlobeIcon />{issue.hostel_name}</span>
      {issue.room_number && <span>Room {issue.room_number}</span>}
      <time dateTime={issue.created_at}>{new Date(issue.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time>
    </div>
    <p className="issue-message">{issue.message}</p>
    {issue.replies.length > 0 ? <div className="issue-replies">
      {issue.replies.map((reply) => <div className="issue-reply" key={reply.id}>
        <span className="issue-reply-avatar"><ChatIcon /></span>
        <div><div className="issue-reply-heading"><strong>Support team</strong><time dateTime={reply.created_at}>{new Date(reply.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time></div><p className="issue-message">{reply.message}</p></div>
      </div>)}
    </div> : issue.status === 'open' && <p className="issue-waiting"><ClockIcon />Your issue is with the support team. Replies will appear here.</p>}
  </article>
}

export default function IssuesPage() {
  const [account, setAccount] = useState(null)
  const [data, setData] = useState({ items: [], total: 0, open_count: 0 })
  const [offset, setOffset] = useState(0)
  const [form, setForm] = useState({ subject: '', message: '', room_number: '' })
  const [error, setError] = useState('')
  const [historyError, setHistoryError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [signedOut, setSignedOut] = useState(false)

  useEffect(() => {
    document.title = 'Raise an issue | Vlad WiFi'
    let active = true
    getAccount().then((result) => { if (active) setAccount(result) }).catch((err) => {
      if (!active) return
      if (err instanceof AccountApiError && err.status === 401) setSignedOut(true)
      else setError('Your account could not be loaded. Please refresh and try again.')
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!account) return undefined
    let active = true
    async function refresh() {
      try {
        const result = await listIssues(offset)
        if (active) { setData(result); setHistoryError('') }
      } catch (err) {
        if (!active) return
        if (err.status === 401) setSignedOut(true)
        else setHistoryError('Your issue history could not be refreshed. We will try again shortly.')
      } finally { if (active) setHistoryLoading(false) }
    }
    setHistoryLoading(true)
    refresh()
    const timer = window.setInterval(refresh, 30000)
    return () => { active = false; window.clearInterval(timer) }
  }, [account, offset])

  async function submit(event) {
    event.preventDefault()
    if (form.subject.trim().length < 3 || form.message.trim().length < 3) {
      setError('Please enter a subject and complaint of at least 3 characters.')
      return
    }
    setBusy(true); setError(''); setSuccess('')
    try {
      const issue = await createIssue({ subject: form.subject.trim(), message: form.message.trim(), room_number: form.room_number.trim() || null })
      setForm({ subject: '', message: '', room_number: '' })
      setSuccess('Issue sent. Your hostel admin has been notified, and replies will appear in your history below.')
      setOffset(0)
      setData((current) => ({ ...current, items: [issue, ...current.items].slice(0, 30), total: current.total + 1, open_count: current.open_count + 1 }))
      // Keep a successful submission visible even if the history refresh fails.
      try { setData(await listIssues(0)); setHistoryError('') } catch { setHistoryError('Your issue was sent. History will refresh shortly.') }
    } catch (err) {
      if (err.status === 401) setSignedOut(true)
      else setError(err.status === 422 ? 'Enter a subject and complaint of at least 3 characters.' : 'Your issue could not be sent. Please try again. Your message is still here.')
    } finally { setBusy(false) }
  }

  if (loading) return <PageLoadingState title="Loading support" />
  return <div className="account-page"><AccountHeader activePage="issues" />
    <main className="issues-page">
      <header className="issues-heading"><p className="issues-eyebrow">Customer support</p><h1>Raise an issue</h1><p>Connection trouble, a billing question, or something else? We are here to help.</p></header>
      {signedOut ? <section className="issue-card issue-empty issue-signin"><span className="issue-icon-tile"><ShieldIcon /></span><h2>Let us know how we can help</h2><p>Sign in to send a complaint, include your hostel details, and keep track of replies.</p><a className="issue-primary" href="/login">Sign in to raise an issue</a></section> : !account ? <section className="issue-card issue-empty"><span className="issue-icon-tile"><WarningIcon /></span><h2>We could not load your account</h2><p role="alert">{error}</p><button className="issue-primary" onClick={() => window.location.reload()}>Try again</button></section> : <>
        <div className="issues-compose-layout">
          <form className="issue-card issue-form" id="new-issue" onSubmit={submit} aria-busy={busy}>
            <div className="issue-section-heading"><span className="issue-icon-tile"><ChatIcon /></span><div><h2>Tell us what happened</h2><p>A few details will help us look into it.</p></div></div>
            <div className="issue-hostel-context"><GlobeIcon /><div><small>Reporting from</small><strong>{account.hostel_name || 'Your hostel'}</strong></div><span>Included automatically</span></div>
            <fieldset disabled={busy}>
              <div className="issue-form-row">
                <label htmlFor="issue-subject">Subject<input id="issue-subject" required minLength={3} maxLength={160} value={form.subject} placeholder="A short summary of the issue" onChange={(e) => setForm({ ...form, subject: e.target.value })} /></label>
                <label htmlFor="issue-room">Room number <small>Optional</small><input id="issue-room" maxLength={40} value={form.room_number} placeholder="e.g. B12" onChange={(e) => setForm({ ...form, room_number: e.target.value })} /></label>
              </div>
              <label htmlFor="issue-message">Your complaint<textarea id="issue-message" required minLength={3} maxLength={5000} rows={6} value={form.message} placeholder="Describe the problem, when it started, and anything you have already tried." aria-describedby="issue-message-hint" onChange={(e) => setForm({ ...form, message: e.target.value })} /></label>
              <div className="issue-field-hint" id="issue-message-hint"><span>Please leave out passwords and payment details.</span><span>{form.message.length.toLocaleString()} / 5,000</span></div>
            </fieldset>
            {error && <p className="issue-alert issue-error" role="alert"><WarningIcon />{error}</p>}
            {success && <p className="issue-alert issue-success" role="status"><CheckIcon />{success}</p>}
            <div className="issue-form-footer"><p><ShieldIcon /><span>Visible only to you and our support team.</span></p><button className="issue-primary" disabled={busy} type="submit">{busy ? <span className="issue-spinner" /> : <SendIcon />}{busy ? 'Sending...' : 'Send issue'}</button></div>
          </form>
          <aside className="issues-sidebar" aria-label="Support information">
            <section className="issue-card issue-guide"><p className="issues-eyebrow">Here to help</p><h2>What happens next?</h2><ol>
              <li><span>1</span><div><h3>Send your issue</h3><p>Your hostel and room details help us find the right place to help.</p></div></li>
              <li><span>2</span><div><h3>We look into it</h3><p>Your hostel admin receives a notification and reviews your complaint.</p></div></li>
              <li><span>3</span><div><h3>Follow the conversation</h3><p>Check your issue history below for updates and replies.</p></div></li>
            </ol></section>
            <section className="issue-card issue-summary"><div><ChatIcon /><h2>Your support activity</h2></div><dl><div><dt>Issues raised</dt><dd>{historyLoading ? '—' : data.total}</dd></div><div><dt>Awaiting attention</dt><dd>{historyLoading ? '—' : data.open_count}</dd></div></dl><a href="#issue-history">View issue history <span aria-hidden="true">↓</span></a></section>
          </aside>
        </div>
        <section className="issues-history" id="issue-history" aria-labelledby="issue-history-title" aria-busy={historyLoading}>
          <div className="issues-history-heading"><div><h2 id="issue-history-title">Your issue history <span>{data.total}</span></h2><p>All your complaints and support replies, in one place.</p></div><span className="issues-history-note"><ClockIcon />Updates automatically</span></div>
          {historyError && <p className="issue-alert issue-error" role="alert"><WarningIcon />{historyError}</p>}
          {historyLoading ? <div className="issue-card issue-history-loading" role="status"><span className="issue-spinner" />Loading your issue history...</div> : !data.items.length ? <div className="issue-card issue-empty"><span className="issue-icon-tile"><ChatIcon /></span><h3>{historyError ? 'History is temporarily unavailable' : 'No issues here yet'}</h3><p>{historyError ? 'Your existing complaints will appear when the connection is restored.' : 'When you send an issue, you can follow its progress and read replies here.'}</p>{!historyError && <a href="#new-issue">Raise your first issue <span aria-hidden="true">↑</span></a>}</div> : data.items.map((issue) => <IssueHistoryCard key={issue.id} issue={issue} />)}
          {data.total > 30 && <nav className="issue-pagination" aria-label="Issue history pages"><button disabled={!offset || historyLoading} onClick={() => setOffset(Math.max(0, offset - 30))}>Previous</button><span>{offset + 1}–{Math.min(offset + 30, data.total)} of {data.total}</span><button disabled={offset + 30 >= data.total || historyLoading} onClick={() => setOffset(offset + 30)}>Next</button></nav>}
        </section>
      </>}
    </main>
  </div>
}
