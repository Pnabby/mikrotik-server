import { useCallback, useEffect, useState } from 'react'

import { listIssues, updateIssue } from '../services/adminApi'
import './issues.css'

function IssueCard({ issue, canEdit, onUpdated, onSessionExpired }) {
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function save(payload) {
    setBusy(true); setError('')
    try {
      const updated = await updateIssue(issue.id, payload)
      setReply(''); onUpdated(updated)
      window.dispatchEvent(new Event('vlad:issues-updated'))
    } catch (err) {
      if (err.status === 401) onSessionExpired()
      else setError('The issue could not be updated. Please try again.')
    } finally { setBusy(false) }
  }
  return <article className="admin-issue-card">
    <div className="admin-issue-heading"><h2>{issue.subject}</h2><span className={`admin-issue-status ${issue.status}`}>{issue.status === 'attended' ? 'Attended to' : 'Awaiting attention'}</span></div>
    <div className="admin-issue-meta"><strong>{issue.hostel_name}</strong><span>{issue.username}</span><span>{issue.room_number ? `Room ${issue.room_number}` : 'Room not provided'}</span><time>{new Date(issue.created_at).toLocaleString()}</time></div>
    <p className="admin-issue-message">{issue.message}</p>
    {issue.replies.map((entry) => <div className="admin-issue-reply" key={entry.id}><strong>Admin reply</strong><small>{new Date(entry.created_at).toLocaleString()}</small><p className="admin-issue-message">{entry.message}</p></div>)}
    {canEdit && <form onSubmit={(e) => { e.preventDefault(); if (reply.trim()) save({ reply: reply.trim() }) }}>
      <label>Reply to {issue.username}<textarea required maxLength={5000} rows={3} disabled={busy} value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Write a reply the customer can read in their issues page." /></label>
      <div className="admin-issue-actions"><button disabled={busy || !reply.trim()} type="submit">{busy ? 'Saving…' : 'Send reply'}</button><button disabled={busy} type="button" onClick={() => save({ status: issue.status === 'attended' ? 'open' : 'attended' })}>{issue.status === 'attended' ? 'Reopen issue' : 'Mark as attended to'}</button></div>
    </form>}
    {error && <p className="admin-issue-error" role="alert">{error}</p>}
  </article>
}

export default function IssuesPanel({ hostels, canEdit, onSessionExpired }) {
  const [filters, setFilters] = useState({ router_id: '', issue_status: 'open', offset: 0 })
  const [data, setData] = useState({ items: [], total: 0, open_count: 0 })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const load = useCallback(async () => {
    try { setData(await listIssues(filters)); setError('') }
    catch (err) {
      if (err.status === 401) onSessionExpired()
      else setError('Issues could not be loaded. Please try again.')
    } finally { setLoading(false) }
  }, [filters, onSessionExpired])
  useEffect(() => {
    let active = true
    async function refresh() {
      try { const result = await listIssues(filters); if (active) { setData(result); setError('') } }
      catch (err) { if (active) { if (err.status === 401) onSessionExpired(); else setError('Issues could not be loaded. Please try again.') } }
      finally { if (active) setLoading(false) }
    }
    setLoading(true); refresh()
    const timer = window.setInterval(refresh, 30000)
    return () => { active = false; window.clearInterval(timer) }
  }, [filters, onSessionExpired])

  return <section className="admin-issues-panel">
    <div className="dashboard-page-heading"><div><p className="dashboard-kicker">Customer support</p><h1>Issues &amp; complaints</h1><p>{data.open_count} awaiting attention{filters.router_id ? ' at this hostel' : ' across all hostels'}.</p></div><button type="button" onClick={load}>Refresh</button></div>
    <div className="admin-issue-filters"><label>Hostel<select value={filters.router_id} onChange={(e) => setFilters({ ...filters, router_id: e.target.value, offset: 0 })}><option value="">All hostels</option>{hostels.map((h) => <option key={h.router_id} value={h.router_id}>{h.name}</option>)}</select></label><label>Status<select value={filters.issue_status} onChange={(e) => setFilters({ ...filters, issue_status: e.target.value, offset: 0 })}><option value="open">Awaiting attention</option><option value="attended">Attended to</option><option value="">All issues</option></select></label></div>
    {error && <p className="admin-issue-error" role="alert">{error}</p>}
    {loading ? <p role="status">Loading issues…</p> : !data.items.length ? <p className="admin-issue-card">No issues match these filters.</p> : data.items.map((issue) => <IssueCard key={issue.id} issue={issue} canEdit={canEdit} onSessionExpired={onSessionExpired} onUpdated={(updated) => {
      setData((current) => ({ ...current, items: current.items.map((item) => item.id === updated.id ? updated : item) }))
      load()
    }} />)}
    {data.total > 30 && <div className="admin-issue-pagination"><button disabled={!filters.offset} onClick={() => setFilters({ ...filters, offset: Math.max(0, filters.offset - 30) })}>Previous</button><span>{filters.offset + 1}–{Math.min(filters.offset + 30, data.total)} of {data.total}</span><button disabled={filters.offset + 30 >= data.total} onClick={() => setFilters({ ...filters, offset: filters.offset + 30 })}>Next</button></div>}
  </section>
}
