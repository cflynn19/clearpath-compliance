import { useEffect, useState } from 'react'
import { CHANNELS, getMetrics, PRODUCTS, STATUS_LABEL } from '../api'
import type { AssetStatus, AssetSummary, Channel, Metrics, Product } from '../api'
import { duration, timeAgo } from '../format'
import { href } from '../router'

const FILTERS: { key: AssetStatus | 'all'; label: string }[] = [
  { key: 'in_review', label: 'In review' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'all', label: 'All' },
]

function FlagSummary({ a }: { a: AssetSummary }) {
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

function MetricsStrip({ m }: { m: Metrics }) {
  const tiles = [
    {
      label: 'Waiting for review',
      value: String(m.in_review),
      sub: m.oldest_waiting_minutes === null ? 'queue clear' : `oldest ${duration(m.oldest_waiting_minutes)}`,
    },
    { label: 'Median time to decision', value: duration(m.median_decision_minutes), sub: 'submitted → decided' },
    { label: 'Decided', value: String(m.approved + m.rejected), sub: `${m.approved} approved · ${m.rejected} rejected` },
    { label: 'Flags per ad', value: m.flags_per_ad === null ? '–' : m.flags_per_ad.toFixed(1), sub: 'code + AI' },
    {
      label: 'Flags dismissed',
      value: m.dismiss_rate === null ? '–' : `${Math.round(m.dismiss_rate * 100)}%`,
      sub: 'of resolved flags',
    },
  ]
  return (
    <section className="metrics" aria-label="Throughput">
      {tiles.map((t) => (
        <div key={t.label} className="card metric">
          <span className="metric-label">{t.label}</span>
          <strong>{t.value}</strong>
          <span className="metric-sub">{t.sub}</span>
        </div>
      ))}
    </section>
  )
}

export function Queue({ assets }: { assets: AssetSummary[] | null }) {
  const [filter, setFilter] = useState<AssetStatus | 'all'>('in_review')
  const [metrics, setMetrics] = useState<Metrics | null>(null)

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
      (!q || a.title.toLowerCase().includes(q) || a.submitter.toLowerCase().includes(q)),
  )
  const shown = matching.filter((a) => filter === 'all' || a.status === filter)
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
          <p className="muted">
            Marketing waiting for compliance review. Every ad arrives already checked: open one to resolve its flags and
            make the call.
          </p>
        </div>
        <a className="btn primary" href={href.new}>
          New check
        </a>
      </div>

      {metrics && <MetricsStrip m={metrics} />}

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
                      {a.submitter} · {timeAgo(a.created_at)}
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
