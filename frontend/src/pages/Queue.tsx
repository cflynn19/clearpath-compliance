import { useEffect, useState } from 'react'
import { CHANNELS, getMetrics, getRules, PRODUCTS, STATUS_LABEL } from '../api'
import type { AssetStatus, AssetSummary, Channel, Metrics, Product } from '../api'
import { duration, timeAgo, waitingSince } from '../format'
import { href } from '../router'

const FILTERS: { key: AssetStatus | 'all'; label: string }[] = [
  { key: 'in_review', label: 'In review' },
  { key: 'needs_changes', label: 'Changes requested' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'all', label: 'All' },
]

function FlagSummary({ a }: { a: AssetSummary }) {
  if (a.status === 'needs_changes') return <span className="pill judge">With submitter</span>
  if (a.status !== 'in_review') return null
  if (!a.open_failed && !a.open_judgment) {
    return <span className="pill ok">{a.total ? 'All flags resolved' : 'No flags'}</span>
  }
  return (
    <>
      {a.open_failed > 0 && <span className="pill fail">{a.open_failed} failed</span>}
      {a.open_judgment > 0 && <span className="pill judge">{a.open_judgment} to judge</span>}
    </>
  )
}

export function Queue({ assets, rule }: { assets: AssetSummary[] | null; rule?: string }) {
  // Arriving from Insights' "View ads", show every status: the point is to see where the rule fired.
  const [filter, setFilter] = useState<AssetStatus | 'all'>(rule ? 'all' : 'in_review')
  const [ruleName, setRuleName] = useState<string | null>(null)
  const [metrics, setMetrics] = useState<Metrics | null>(null)

  useEffect(() => {
    if (!rule) return
    getRules()
      .then((rs) => setRuleName(rs.find((r) => r.id === rule)?.name ?? rule))
      .catch(() => setRuleName(rule))
  }, [rule])

  // Refetch whenever the queue changes (a decision, a reset, a new check).
  useEffect(() => {
    getMetrics()
      .then(setMetrics)
      .catch(() => setMetrics(null))
  }, [assets])
  const [product, setProduct] = useState<Product | ''>('')
  const [channel, setChannel] = useState<Channel | ''>('')
  const [search, setSearch] = useState('')
  const [failedOnly, setFailedOnly] = useState(false)

  if (assets === null) return <p className="muted">Loading the queue…</p>

  // Status tabs count everything that matches the other filters.
  const q = search.trim().toLowerCase()
  const matching = assets.filter(
    (a) =>
      (!product || a.product === product) &&
      (!channel || a.channel === channel) &&
      (!failedOnly || a.open_failed > 0) &&
      (!rule || a.rule_ids.includes(rule)) &&
      (!q || a.title.toLowerCase().includes(q) || a.submitter.toLowerCase().includes(q)),
  )
  // A queue is first in, first out: the ad that has waited longest is the most urgent.
  // Decided ads are history, so the most recent decision comes first.
  const time = (iso: string | null) => (iso ? new Date(iso).getTime() : 0)
  const shown = matching
    .filter((a) => filter === 'all' || a.status === filter)
    .sort((a, b) => {
      // In review, then waiting on the submitter, then decided.
      const rank = (x: AssetSummary) => (x.status === 'in_review' ? 0 : x.status === 'needs_changes' ? 1 : 2)
      if (rank(a) !== rank(b)) return rank(a) - rank(b)
      return rank(a) < 2 ? time(a.created_at) - time(b.created_at) : time(b.decided_at) - time(a.decided_at)
    })
  const count = (key: AssetStatus | 'all') => matching.filter((a) => key === 'all' || a.status === key).length
  const filtered = Boolean(product || channel || failedOnly || q)
  const clear = () => {
    setProduct('')
    setChannel('')
    setSearch('')
    setFailedOnly(false)
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Review queue</h1>
          <p className="muted">Every ad arrives already checked. Open one to review it.</p>
        </div>
        <a className="btn primary" href={href.new}>
          New check
        </a>
      </div>

      {metrics && (
        <p className="backlog">
          <b>{metrics.in_review} waiting</b>
          {metrics.oldest_waiting_minutes !== null && <> · oldest {duration(metrics.oldest_waiting_minutes)}</>}
          {' · '}
          <a href={href.insights}>Team insights →</a>
        </p>
      )}

      {rule && (
        <p className="rule-filter">
          Showing ads flagged by <b>{ruleName ?? '…'}</b>
          <a className="btn small ghost" href={href.queue}>
            Clear
          </a>
        </p>
      )}

      <div className="filters">
        <input
          type="search"
          className="search"
          placeholder="Search title or submitter"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select value={product} onChange={(e) => setProduct(e.target.value as Product | '')}>
          <option value="">All products</option>
          {Object.entries(PRODUCTS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select value={channel} onChange={(e) => setChannel(e.target.value as Channel | '')}>
          <option value="">All channels</option>
          {Object.entries(CHANNELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <label className="toggle">
          <input type="checkbox" checked={failedOnly} onChange={(e) => setFailedOnly(e.target.checked)} />
          Has failed checks
        </label>
        {filtered && (
          <button className="btn small ghost" onClick={clear}>
            Clear filters
          </button>
        )}
      </div>

      <div className="tabs">
        {FILTERS.map((f) => (
          <button key={f.key} className={filter === f.key ? 'on' : ''} onClick={() => setFilter(f.key)}>
            {f.label} <span>{count(f.key)}</span>
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <div className="card empty-state">
          {assets.length === 0 ? (
            <>
              <strong>The demo queue is loading.</strong>
              <p className="muted">
                The first start checks every sample ad with AI, which takes about a minute. Refresh shortly, or use
                Reset demo.
              </p>
            </>
          ) : (
            <p className="muted">
              {filtered ? 'No ads match these filters.' : 'Nothing here.'}{' '}
              {filtered && (
                <button className="btn small ghost" onClick={clear}>
                  Clear filters
                </button>
              )}
            </p>
          )}
        </div>
      ) : (
        <ul className="queue">
          {shown.map((a) => (
            <li key={a.id}>
              <a className="card queue-item" href={href.review(a.id)}>
                <div className="queue-main">
                  <strong>{a.title}</strong>
                  <div className="meta">
                    <span className="tag">{PRODUCTS[a.product]}</span>
                    <span className="tag">{CHANNELS[a.channel]}</span>
                    <span className="muted">
                      {a.submitter} ·{' '}
                      {a.status === 'in_review'
                        ? `waiting ${waitingSince(a.created_at)}`
                        : a.status === 'needs_changes'
                          ? 'sent back for changes'
                          : `decided ${timeAgo(a.decided_at ?? a.created_at)}`}
                    </span>
                  </div>
                </div>
                <div className="queue-side">
                  <FlagSummary a={a} />
                  <span className={`state state-${a.status}`}>{STATUS_LABEL[a.status]}</span>
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
