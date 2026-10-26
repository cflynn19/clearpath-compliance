import { useEffect, useState } from 'react'
import { CHANNELS, getRules, PRODUCTS } from '../api'
import type { FlagType, ReviewConfig, Rule } from '../api'
import { shortReason } from '../format'

const SECTIONS: { type: FlagType; title: string; blurb: string }[] = [
  {
    type: 'check_failed',
    title: 'Code checks',
    blurb: 'Definite, yes/no rules. Free, instant and consistent: the same ad always gets the same result.',
  },
  {
    type: 'needs_judgment',
    title: 'AI judgment checks',
    blurb:
      'Rules about meaning and context. The AI must quote the exact text it flags; anything it cannot quote is discarded.',
  },
]

function scope(rule: Rule) {
  const parts = [
    rule.products.length ? rule.products.map((p) => PRODUCTS[p]).join(', ') : 'All products',
    rule.channels.length ? rule.channels.map((c) => CHANNELS[c]).join(', ') : 'all channels',
  ]
  return parts.join(' · ')
}

function Stats({ rule, reasons }: { rule: Rule; reasons: Record<string, string> }) {
  const { flagged, dismissed } = rule.stats
  if (!flagged) return <span className="muted small">Not triggered yet</span>
  const top = Object.entries(rule.stats.reasons).sort((a, b) => b[1] - a[1])[0]
  const rate = Math.round((dismissed / flagged) * 100)
  return (
    <span className="small">
      Flagged {flagged}× · <b className={rate >= 50 ? 'warn' : ''}>dismissed {rate}%</b>
      {top && <span className="muted"> · mostly “{shortReason(reasons, top[0])}”</span>}
    </span>
  )
}

export function Rules({ config }: { config: ReviewConfig | null }) {
  const [rules, setRules] = useState<Rule[] | null>(null)

  useEffect(() => {
    getRules().then(setRules).catch(() => setRules([]))
  }, [])

  if (!rules) return <p className="muted">Loading rules…</p>
  const reasons = config?.dismiss_reasons ?? {}

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Rules</h1>
          <p className="muted">
            What every ad is checked against, and why. A rule that reviewers dismiss most of the time is a rule worth
            fixing. Based on public federal regulations; illustrative, not legal advice.
          </p>
        </div>
      </div>

      {SECTIONS.map((s) => (
        <section key={s.type} className="rule-section">
          <h2>
            <span className={`badge ${s.type}`}>{s.type === 'check_failed' ? '✕' : '?'}</span> {s.title}
          </h2>
          <p className="muted">{s.blurb}</p>
          <div className="rule-list">
            {rules
              .filter((r) => r.type === s.type)
              .map((r) => (
                <div key={r.id} className="card rule">
                  <div className="rule-head">
                    <strong>{r.name}</strong>
                    <span className="cite">{r.citation}</span>
                  </div>
                  <p>{r.description}</p>
                  <div className="rule-foot">
                    <span className="muted small">{scope(r)}</span>
                    <Stats rule={r} reasons={reasons} />
                  </div>
                </div>
              ))}
          </div>
        </section>
      ))}
    </>
  )
}
