import { useEffect, useState } from 'react'

import AccountHeader from '../components/AccountHeader'
import PageLoadingState from '../components/PageLoadingState'
import { AccountApiError, createIssue, getAccount, listIssues } from '../services/accountApi'
import '../styles/issues.css'

export default function IssuesPage() {
  const [account, setAccount] = useState(null)
  const [data, setData] = useState({ items: [], total: 0 })
  const [offset, setOffset] = useState(0)
  const [form, setForm] = useState({ subject: '', message: '', room_number: '' })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
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
        if (active) setData(result)
      } catch (err) {
        if (!active) return
        if (err.status === 401) setSignedOut(true)
        else setError('Issues could not be refreshed. Please try again.')
      }
    }
    refresh()
    const timer = window.setInterval(refresh, 30000)
    return () => { active = false; window.clearInterval(timer) }
  }, [account, offset])

  async function submit(event) {
    event.preventDefault()
    setBusy(true); setError(''); setSuccess('')
    try {
      const issue = await createIssue({ ...form, room_number: form.room_number.trim() || null })
      setForm({ subject: '', message: '', room_number: '' })
      setSuccess('Your issue has been sent to the admin. Replies will appear below.')
      setOffset(0)
      setData((current) => ({ ...current, items: [issue, ...current.items].slice(0, 30), total: current.total + 1 }))
      // A history refresh failure must not make a successful submission look unsuccessful.
      try { setData(await listIssues(0)) } catch { setError('Your issue was sent. History will refresh shortly.') }
    } catch (err) {
      if (err.status === 401) setSignedOut(true)
      else setError(err.status === 422 ? 'Enter a subject and complaint of at least 3 characters.' : 'Your issue could not be sent. Please try again.')
    } finally { setBusy(false) }
  }

  if (loading) return <PageLoadingState title="Loading support" />
  return <div className="account-page"><AccountHeader activePage="issues" />
    <main className="issues-page">
      <div className="issues-heading"><h1>Raise an issue</h1><p>Tell us about a connection problem, billing question, or any other complaint.</p></div>
      {signedOut ? <section className="issue-card"><h2>Sign in to raise an issue</h2><p>Your account tells us which hostel needs help and keeps your replies private.</p><a className="issue-primary" href="/login">Sign in</a></section> : <>
        <form className="issue-card issue-form" onSubmit={submit}>
          <p>Reporting from <strong>{account?.hostel_name || 'your hostel'}</strong></p>
          <label>Room number <small>Optional</small><input maxLength={40} value={form.room_number} placeholder="e.g. B12" onChange={(e) => setForm({ ...form, room_number: e.target.value })} /></label>
          <label>Subject<input required minLength={3} maxLength={160} value={form.subject} placeholder="What do you need help with?" onChange={(e) => setForm({ ...form, subject: e.target.value })} /></label>
          <label>Your complaint<textarea required minLength={3} maxLength={5000} rows={5} value={form.message} placeholder="Describe what happened and how we can help." onChange={(e) => setForm({ ...form, message: e.target.value })} /></label>
          <button className="issue-primary" disabled={busy || !account} type="submit">{busy ? 'Sending…' : 'Send issue'}</button>
        </form>
        {success && <p className="issue-success" role="status">{success}</p>}
        <div className="issues-heading"><h2>Your issues</h2><p>Follow the status of your complaints and read replies from support.</p></div>
        {!data.items.length && <p className="issue-card">You have no issues on this page.</p>}
        {data.items.map((issue) => <article className="issue-card" key={issue.id}>
          <div className="issue-title"><h3>{issue.subject}</h3><span className={`issue-status ${issue.status}`}>{issue.status === 'attended' ? 'Attended to' : 'Awaiting attention'}</span></div>
          <small>{issue.hostel_name}{issue.room_number ? ` · Room ${issue.room_number}` : ''} · {new Date(issue.created_at).toLocaleString()}</small>
          <p className="issue-message">{issue.message}</p>
          {issue.replies.map((reply) => <div className="issue-reply" key={reply.id}><strong>Support reply</strong><small>{new Date(reply.created_at).toLocaleString()}</small><p className="issue-message">{reply.message}</p></div>)}
        </article>)}
        {data.total > 30 && <div className="issue-pagination"><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 30))}>Previous</button><span>{offset + 1}–{Math.min(offset + 30, data.total)} of {data.total}</span><button disabled={offset + 30 >= data.total} onClick={() => setOffset(offset + 30)}>Next</button></div>}
      </>}
      {error && <p className="issue-error" role="alert">{error}</p>}
    </main>
  </div>
}
