import { Fragment, useCallback, useEffect, useState } from 'react'
import { deleteRule, getMetrics, getRules, toggleRule } from '../api'
import type { Metrics, ReviewConfig, Rule, RuleHealth } from '../api'
import { duration, shortReason } from '../format'
import { ListIcon, PowerIcon, RuleIcon, TrashIcon } from '../icons'
import { href } from '../router'
import { RowMenu } from '../RowMenu'
import { SwitchOffConfirm } from '../SwitchOff'

const RANGES: { days?: number; label: string }[] = [
  { days: 1, label: 'Last 24 hours' },
  { days: 7, label: 'Last 7 days' },
  { label: 'All time' },
]

// The most common dismissal reason says what to do about a rule (DECISIONS D17): a short
// tag in the table, the full explanation on hover.
const GUIDANCE: Record<string, { tag: string; detail: string }> = {
  false_positive: { tag: 'may be too broad', detail: 'Reviewers say it fires when it shouldn’t.' },
  met_elsewhere: {
    tag: 'missing context',
    detail: 'Usually met on a linked page or footer the rule can’t see. Not a rule problem.',
  },
  approved_exception: { tag: 'policy question', detail: 'Mostly legal-approved exceptions: a question for legal.' },
  other: { tag: 'mixed reasons', detail: 'Read the dismissal notes on the flagged ads.' },
}

type SortKey = 'rule_name' | 'type' | 'flagged' | 'dismissed' | 'rate' | 'top_reason'
type Sort = { key: SortKey; dir: 'asc' | 'desc' } | null

const COLUMNS: { key: SortKey; label: string; numeric: boolean }[] = [
  { key: 'rule_name', label: 'Rule', numeric: false },
  { key: 'type', label: 'Type', numeric: false },
  { key: 'flagged', label: 'Flagged', numeric: true },
  { key: 'dismissed', label: 'Dismissed', numeric: true },
  { key: 'rate', label: 'Dismiss rate', numeric: true },
  { key: 'top_reason', label: 'Top reason', numeric: false },
]

const rate = (r: RuleHealth) => r.dismissed / r.flagged

// Click: sort (numbers high-to-low first, text A-Z first). Again: reverse. Third: clear,
// back to the default ranking. One column at a time.
function nextSort(sort: Sort, key: SortKey, numeric: boolean): Sort {
  const first = numeric ? 'desc' : 'asc'
  if (sort?.key !== key) return { key, dir: first }
  if (sort.dir === first) return { key, dir: first === 'desc' ? 'asc' : 'desc' }
  return null
}

function percent(n: number | null) {
  return n === null ? '–' : `${Math.round(n * 100)}%`
}

export function Insights({ config }: { config: ReviewConfig | null }) {
  const [range, setRange] = useState(2)
  const [m, setM] = useState<Metrics | null>(null)
  const [rules, setRules] = useState<Record<string, Rule>>({})
  const [sort, setSort] = useState<Sort>(null)
  const [confirming, setConfirming] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadRules = useCallback(
    (list?: Rule[]) =>
      (list ? Promise.resolve(list) : getRules()).then((rs) => setRules(Object.fromEntries(rs.map((r) => [r.id, r])))),
    [],
  )

  useEffect(() => {
    getMetrics(RANGES[range].days)
      .then(setM)
      .catch(() => setM(null))
  }, [range])
  useEffect(() => {
    loadRules().catch(() => setRules({}))
  }, [loadRules])

  async function act(fn: () => Promise<Rule[]>) {
    setBusy(true)
    setError(null)
    try {
      await loadRules(await fn())
      setConfirming(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const minSample = config?.min_sample ?? 3
  const reasons = config?.dismiss_reasons ?? {}

  const tiles = m && [
    {
      label: 'Waiting for review',
      value: String(m.in_review),
      sub: m.oldest_waiting_minutes === null ? 'queue clear' : `oldest ${duration(m.oldest_waiting_minutes)}`,
      link: href.queue,
    },
    {
      label: 'Median time to decision',
      value: duration(m.median_decision_minutes),
      sub: m.median_decision_minutes === null ? 'no decisions yet' : 'submission to decision',
    },
    { label: 'Decided', value: String(m.approved + m.rejected), sub: `${m.approved} approved · ${m.rejected} rejected` },
    {
      label: 'Submitted',
      value: String(m.submitted),
      sub: m.flags_per_ad === null ? 'no ads yet' : `${m.flags_per_ad.toFixed(1)} flags per ad`,
    },
    { label: 'Flags dismissed', value: percent(m.dismiss_rate), sub: 'of resolved flags' },
  ]

  const sorted = m ? [...m.rule_health] : []
  if (sort) {
    const value = (r: RuleHealth): string | number =>
      sort.key === 'rate' ? rate(r) : sort.key === 'top_reason' ? shortReason(reasons, r.top_reason) : r[sort.key]
    sorted.sort((a, b) => {
      const [x, y] = [value(a), value(b)]
      const cmp = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))
      return sort.dir === 'asc' ? cmp : -cmp
    })
  }

  function menuItems(h: RuleHealth) {
    const rule = rules[h.rule_id]
    return [
      { label: 'View flagged ads', icon: <ListIcon />, href: href.queueForRule(h.rule_id) },
      ...(rule ? [{ label: 'View rule', icon: <RuleIcon />, href: href.rule(h.rule_id) }] : []),
      ...(rule?.enabled
        ? [{ label: 'Switch off…', icon: <PowerIcon />, danger: true, onSelect: () => setConfirming(h.rule_id) }]
        : []),
      ...(rule?.source === 'custom'
        ? [{ label: 'Delete rule', icon: <TrashIcon />, danger: true, onSelect: () => act(() => deleteRule(rule.id)) }]
        : []),
    ]
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Team insights</h1>
          <p className="muted">Team throughput and rule health.</p>
        </div>
      </div>

      <div className="tabs">
        {RANGES.map((r, i) => (
          <button key={r.label} className={range === i ? 'on' : ''} onClick={() => setRange(i)}>
            {r.label}
          </button>
        ))}
      </div>

      {!m || !tiles ? (
        <p className="muted">Loading…</p>
      ) : (
        <>
          <section className="metrics" aria-label="Throughput">
            {tiles.map((t) => {
              const body = (
                <>
                  <span className="metric-label">{t.label}</span>
                  <strong>{t.value}</strong>
                  <span className="metric-sub">{t.sub}</span>
                </>
              )
              return t.link ? (
                <a key={t.label} className="card metric link" href={t.link}>
                  {body}
                </a>
              ) : (
                <div key={t.label} className="card metric">
                  {body}
                </div>
              )
            })}
          </section>

          <section className="card insight-panel">
            <div className="eyebrow">Rule health</div>
            {error && <p className="error">{error}</p>}
            {sorted.length === 0 ? (
              <p className="muted small">No rules fired in this period.</p>
            ) : (
              <div className="table-wrap">
                <table className="health-table">
                  <thead>
                    <tr>
                      {COLUMNS.map((c) => {
                        const active = sort?.key === c.key
                        return (
                          <th
                            key={c.key}
                            className={c.numeric ? 'num' : ''}
                            aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                          >
                            <button className={active ? 'on' : ''} onClick={() => setSort(nextSort(sort, c.key, c.numeric))}>
                              {c.label}
                              <span className="sort-arrow">{active ? (sort.dir === 'asc' ? '▲' : '▼') : ''}</span>
                            </button>
                          </th>
                        )
                      })}
                      <th aria-label="Actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((h) => {
                      const rule = rules[h.rule_id]
                      const small = h.flagged < minSample
                      const guidance = h.top_reason ? GUIDANCE[h.top_reason] : undefined
                      return (
                        <Fragment key={h.rule_id}>
                          <tr className={small ? 'small-sample' : ''}>
                            <td>
                              <a href={href.queueForRule(h.rule_id)} title="View flagged ads">
                                {h.rule_name}
                              </a>
                              {rule && !rule.enabled && <span className="chip">Off</span>}
                              {rule?.source === 'custom' && <span className="chip custom">Custom</span>}
                              {!rule && <span className="chip">Deleted</span>}
                            </td>
                            <td>
                              <span className={`badge ${h.type} inline`} title={h.type === 'check_failed' ? 'Code' : 'AI'}>
                                {h.type === 'check_failed' ? '✕' : '?'}
                              </span>{' '}
                              {h.type === 'check_failed' ? 'Code' : 'AI'}
                            </td>
                            <td className="num">{h.flagged}</td>
                            <td className="num">{h.dismissed}</td>
                            <td className="num">
                              {small ? (
                                <span className="tag-note muted-tag" title={`Fewer than ${minSample} flags: too early to judge.`}>
                                  too few to tell
                                </span>
                              ) : (
                                <span className="rate">
                                  <span className="rate-bar">
                                    <i
                                      className={rate(h) >= 0.5 ? 'high' : ''}
                                      style={{ width: `${Math.round(rate(h) * 100)}%` }}
                                    />
                                  </span>
                                  <b className={rate(h) >= 0.5 ? 'warn' : ''}>{percent(rate(h))}</b>
                                </span>
                              )}
                            </td>
                            <td>
                              {h.top_reason ? (
                                <>
                                  {shortReason(reasons, h.top_reason)}
                                  {!small && guidance && (
                                    <span className="tag-note" title={guidance.detail}>
                                      {guidance.tag}
                                    </span>
                                  )}
                                </>
                              ) : (
                                <span className="muted">–</span>
                              )}
                            </td>
                            <td className="actions-cell">
                              <RowMenu label={`Actions for ${h.rule_name}`} items={menuItems(h)} />
                            </td>
                          </tr>
                          {confirming === h.rule_id && rule && (
                            <tr className="confirm-row">
                              <td colSpan={COLUMNS.length + 1}>
                                <SwitchOffConfirm
                                  name={rule.name}
                                  builtin={rule.source === 'builtin'}
                                  busy={busy}
                                  onCancel={() => setConfirming(null)}
                                  onConfirm={(note) => act(() => toggleRule(rule.id, false, note))}
                                />
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <p className="muted small">Demo data since the last reset.</p>
        </>
      )}
    </>
  )
}
