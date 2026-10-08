import { useCallback, useEffect, useRef, useState } from 'react'

import { listIssues, updateIssue } from '../services/adminApi'
import './issues.css'

function SupportIcon({ name }) {
  const paths = {
    message: <><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8Z" /><path d="M8 10h8M8 14h5" /></>,
    send: <path d="m22 2-7 20-4-9-9-4 20-7ZM22 2 11 13" />,
    building: <><path d="M5 21V5l10-3v19M15 10h4v11M3 21h18M9 7h2M9 11h2M9 15h2" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    refresh: <><path d="M20 5v6h-6" /><path d="M20 11A8 8 0 1 0 18.3 16" /></>,
    back: <path d="m10 5-7 7 7 7M3 12h18" />,
    alert: <><path d="m12 3 10 18H2L12 3ZM12 9v4M12 17h.01" /></>,
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>
}

function IssueStatus({ status }) {
  return <span className={`admin-issue-status ${status}`}><SupportIcon name={status === 'attended' ? 'check' : 'clock'} />{status === 'attended' ? 'Attended to' : 'Awaiting attention'}</span>
}

function formatDate(value, compact = false) {
  return new Date(value).toLocaleString(undefined, compact ? { month: 'short', day: 'numeric' } : { dateStyle: 'medium', timeStyle: 'short' })
}

function IssueDetail({ issue, canEdit, reply, onReplyChange, onUpdated, onSessionExpired, onBack }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function save(payload) {
    setBusy(true); setError('')
    try {
      const updated = await updateIssue(issue.id, payload)
      if (payload.reply) onReplyChange('')
      onUpdated(updated, payload.reply ? 'Reply sent. The customer can read it in their issue history.' : updated.status === 'attended' ? 'Issue marked as attended to.' : 'Issue reopened and added to the attention queue.')
      window.dispatchEvent(new Event('vlad:issues-updated'))
    } catch (err) {
      if (err.status === 401) onSessionExpired()
      else setError('The issue could not be updated. Please try again. Your reply has been kept.')
    } finally { setBusy(false) }
  }
  return <article className="admin-issue-detail" aria-busy={busy}>
    <button className="admin-issue-back admin-issue-button" onClick={onBack}><SupportIcon name="back" />Back to issues</button>
    <header className="admin-issue-detail-header">
      <div className="admin-issue-heading"><IssueStatus status={issue.status} /><span className="admin-issue-reference">Issue #{issue.id.slice(0, 8)}</span></div>
      <h2 tabIndex={-1}>{issue.subject}</h2>
      <dl className="admin-issue-meta"><div><dt>Customer</dt><dd>{issue.username}</dd></div><div><dt>Hostel</dt><dd>{issue.hostel_name}</dd></div><div><dt>Room</dt><dd>{issue.room_number || 'Not provided'}</dd></div><div><dt>Submitted</dt><dd><time dateTime={issue.created_at}>{formatDate(issue.created_at)}</time></dd></div></dl>
      {canEdit && <button className="admin-issue-button admin-issue-resolve" disabled={busy} type="button" onClick={() => save({ status: issue.status === 'attended' ? 'open' : 'attended' })}><SupportIcon name={issue.status === 'attended' ? 'refresh' : 'check'} />{issue.status === 'attended' ? 'Reopen issue' : 'Mark as attended to'}</button>}
    </header>
    <div className="admin-issue-conversation">
      <p className="admin-issue-section-label">Conversation</p>
      <div className="admin-issue-entry"><span className="admin-issue-avatar">{issue.username.slice(0, 1).toUpperCase()}</span><div><div className="admin-issue-entry-heading"><strong>{issue.username}</strong><time dateTime={issue.created_at}>{formatDate(issue.created_at)}</time></div><p className="admin-issue-message">{issue.message}</p></div></div>
      {issue.replies.map((entry) => <div className="admin-issue-entry admin-issue-reply" key={entry.id}><span className="admin-issue-avatar"><SupportIcon name="message" /></span><div><div className="admin-issue-entry-heading"><strong>Support team</strong><time dateTime={entry.created_at}>{formatDate(entry.created_at)}</time></div><p className="admin-issue-message">{entry.message}</p></div></div>)}
      {!issue.replies.length && <p className="admin-issue-no-replies">No replies yet. {canEdit ? 'Start the conversation below.' : 'Support replies will appear here.'}</p>}
      {issue.status === 'attended' && issue.attended_at && <p className="admin-issue-event"><SupportIcon name="check" />Marked as attended to <time dateTime={issue.attended_at}>{formatDate(issue.attended_at)}</time></p>}
    </div>
    {error && <p className="admin-issue-alert admin-issue-error" role="alert"><SupportIcon name="alert" />{error}</p>}
    {canEdit ? <form className="admin-issue-composer" onSubmit={(e) => { e.preventDefault(); if (reply.trim()) save({ reply: reply.trim() }) }}>
      <label htmlFor={`reply-${issue.id}`}>Reply to {issue.username}</label>
      <textarea id={`reply-${issue.id}`} required maxLength={5000} rows={4} disabled={busy} value={reply} onChange={(e) => onReplyChange(e.target.value)} placeholder="Write a helpful reply or let the customer know what you have done." aria-describedby={`reply-note-${issue.id}`} />
      <div className="admin-issue-composer-footer"><p id={`reply-note-${issue.id}`}>Visible to the customer in their issue history.<span>{reply.length.toLocaleString()} / 5,000 characters</span></p><button className="admin-issue-button admin-issue-send" disabled={busy || !reply.trim()} type="submit">{busy ? <span className="admin-issue-spinner" /> : <SupportIcon name="send" />}{busy ? 'Saving...' : 'Send reply'}</button></div>
    </form> : <p className="admin-issue-readonly">You have view-only access. An administrator or operator can reply and update this issue.</p>}
  </article>
}

export default function IssuesPanel({ hostels, canEdit, onSessionExpired }) {
  const [filters, setFilters] = useState({ router_id: '', issue_status: 'open', offset: 0 })
  const [data, setData] = useState({ items: [], total: 0, open_count: 0 })
  const [selectedId, setSelectedId] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const requestId = useRef(0)
  const inbox = useRef(null)
  const load = useCallback(async () => {
    const request = ++requestId.current
    setRefreshing(true)
    try {
      const result = await listIssues(filters)
      if (request === requestId.current) { setData(result); setError('') }
    } catch (err) {
      if (request !== requestId.current) return
      if (err.status === 401) onSessionExpired()
      else setError('Issues could not be refreshed. Please try again.')
    } finally { if (request === requestId.current) { setLoading(false); setRefreshing(false) } }
  }, [filters, onSessionExpired])

  useEffect(() => {
    setLoading(true)
    load()
    const timer = window.setInterval(load, 30000)
    window.addEventListener('vlad:issues-updated', load)
    return () => { requestId.current += 1; window.clearInterval(timer); window.removeEventListener('vlad:issues-updated', load) }
  }, [load])

  function changeFilters(next) {
    setFilters((current) => ({ ...current, ...next, offset: 0 }))
    setSelectedId(null)
    setMobileDetailOpen(false)
    setNotice('')
    setData({ items: [], total: 0, open_count: 0 })
  }

  const selectedIssue = data.items.find((issue) => issue.id === selectedId) || data.items[0]
  const selectedHostel = hostels.find((hostel) => hostel.router_id === filters.router_id)?.name || 'All hostels'
  useEffect(() => {
    if (!mobileDetailOpen || !window.matchMedia('(max-width: 760px)').matches) return
    const heading = inbox.current?.querySelector('.admin-issue-detail h2')
    heading?.focus({ preventScroll: true })
    heading?.scrollIntoView({ block: 'start' })
  }, [mobileDetailOpen, selectedIssue?.id])

  return <section className="admin-issues-panel">
    <div className="dashboard-page-heading"><div><p className="dashboard-kicker">Customer support</p><h1>Issues &amp; complaints</h1><p>Keep every hostel heard. Review complaints, reply, and track what needs attention.</p></div><button className="admin-issue-button" type="button" disabled={refreshing} onClick={load}><SupportIcon name="refresh" />{refreshing ? 'Refreshing...' : 'Refresh'}</button></div>
    <div className="admin-issue-stats">
      <div><span className="admin-issue-stat-icon attention"><SupportIcon name="clock" /></span><div><p>Awaiting attention</p><strong>{loading ? '—' : data.open_count}</strong><small>{filters.router_id ? 'At this hostel' : 'Across all hostels'}</small></div></div>
      <div><span className="admin-issue-stat-icon"><SupportIcon name="message" /></span><div><p>Matching issues</p><strong>{loading ? '—' : data.total}</strong><small>{filters.issue_status === 'open' ? 'Awaiting attention' : filters.issue_status === 'attended' ? 'Attended to' : 'All statuses'}</small></div></div>
      <div><span className="admin-issue-stat-icon"><SupportIcon name="building" /></span><div><p>Hostel scope</p><strong className="admin-issue-scope-name">{selectedHostel}</strong><small>{filters.router_id ? 'Complaints from this hostel' : 'One inbox for every hostel'}</small></div></div>
    </div>
    <div className="admin-issue-filters"><div className="admin-issue-hostel-filter"><label htmlFor="issues-hostel">Hostel</label><select id="issues-hostel" value={filters.router_id} onChange={(e) => changeFilters({ router_id: e.target.value })}><option value="">All hostels</option>{hostels.map((hostel) => <option key={hostel.router_id} value={hostel.router_id}>{hostel.name}</option>)}</select></div><div className="admin-issue-status-filter"><span>Status</span><div role="group" aria-label="Filter issues by status">{[['open', 'Awaiting attention'], ['attended', 'Attended to'], ['', 'All issues']].map(([value, label]) => <button key={value} type="button" aria-pressed={filters.issue_status === value} onClick={() => changeFilters({ issue_status: value })}>{label}</button>)}</div></div><p><SupportIcon name="clock" />Updates automatically</p></div>
    {error && <div className="admin-issue-alert admin-issue-error" role="alert"><SupportIcon name="alert" /><span>{error}</span><button disabled={refreshing} onClick={load}>Try again</button></div>}
    {notice && <p className="admin-issue-alert admin-issue-success" role="status"><SupportIcon name="check" />{notice}</p>}
    {loading ? <div className="admin-issue-empty" role="status"><span className="admin-issue-spinner" /><h2>Loading your inbox</h2><p>Getting the latest complaints and conversations.</p></div> : !data.items.length ? <div className="admin-issue-empty"><span className="admin-issue-empty-icon"><SupportIcon name={error ? 'alert' : 'message'} /></span><h2>{error ? 'Your inbox is temporarily unavailable' : filters.issue_status === 'open' ? 'No issues awaiting attention' : 'No issues match these filters'}</h2><p>{error ? 'Try refreshing to load your complaints.' : filters.issue_status === 'open' ? 'New complaints will appear here when customers raise an issue.' : 'Choose another hostel or status to see more complaints.'}</p>{!error && <button className="admin-issue-button" onClick={() => changeFilters({ router_id: '', issue_status: '' })}>View all issues</button>}</div> : <div ref={inbox} className={`admin-issue-inbox ${mobileDetailOpen ? 'detail-open' : ''}`}>
      <aside className="admin-issue-list" aria-label="Complaints"><div className="admin-issue-list-heading"><h2>Inbox <span>{data.total}</span></h2><span>Newest first</span></div><div className="admin-issue-list-items">{data.items.map((issue) => <button className={`admin-issue-list-item ${selectedIssue.id === issue.id ? 'selected' : ''}`} key={issue.id} aria-pressed={selectedIssue.id === issue.id} onClick={() => { setSelectedId(issue.id); setMobileDetailOpen(true) }}>
        <div className="admin-issue-list-top"><span className={`admin-issue-dot ${issue.status}`} aria-label={issue.status === 'attended' ? 'Attended to' : 'Awaiting attention'} /><strong>{issue.username}</strong><time dateTime={issue.created_at}>{formatDate(issue.created_at, true)}</time></div>
        <h3>{issue.subject}</h3><p>{issue.message}</p><div className="admin-issue-list-meta"><span><SupportIcon name="building" />{issue.hostel_name}</span>{issue.room_number && <span>Room {issue.room_number}</span>}</div>
      </button>)}</div></aside>
      <IssueDetail key={selectedIssue.id} issue={selectedIssue} canEdit={canEdit} reply={drafts[selectedIssue.id] || ''} onReplyChange={(reply) => setDrafts((current) => ({ ...current, [selectedIssue.id]: reply }))} onSessionExpired={onSessionExpired} onBack={() => {
        setMobileDetailOpen(false)
        window.requestAnimationFrame(() => inbox.current?.querySelector('.admin-issue-list-item.selected')?.focus())
      }} onUpdated={(updated, message) => {
        setData((current) => ({ ...current, items: current.items.map((item) => item.id === updated.id ? updated : item) }))
        setNotice(message)
      }} />
    </div>}
    {data.total > 30 && <nav className="admin-issue-pagination" aria-label="Complaint pages"><button className="admin-issue-button" disabled={!filters.offset || loading} onClick={() => { setFilters({ ...filters, offset: Math.max(0, filters.offset - 30) }); setMobileDetailOpen(false) }}>Previous</button><span>{filters.offset + 1}–{Math.min(filters.offset + 30, data.total)} of {data.total}</span><button className="admin-issue-button" disabled={filters.offset + 30 >= data.total || loading} onClick={() => { setFilters({ ...filters, offset: filters.offset + 30 }); setMobileDetailOpen(false) }}>Next</button></nav>}
  </section>
}
