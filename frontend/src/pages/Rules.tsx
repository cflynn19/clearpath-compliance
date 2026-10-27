import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { CHANNELS, createRule, deleteRule, getRuleHistory, getRules, PRODUCTS, toggleRule } from '../api'
import type { Channel, FlagType, NewRule, Product, ReviewConfig, Rule, RuleEvent } from '../api'
import { clockTime, shortReason, timeAgo } from '../format'
import { SwitchOffConfirm } from '../SwitchOff'

const SECTIONS: { type: FlagType; title: string; blurb: string }[] = [
  {
    type: 'check_failed',
    title: 'Code checks',
    blurb: 'Yes/no and consistent: the same ad always gets the same result.',
  },
  {
    type: 'needs_judgment',
    title: 'AI judgment checks',
    blurb: 'Meaning and context, backed by an exact quote from the ad.',
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

export function Rules({ config, focus }: { config: ReviewConfig | null; focus?: string }) {
  const [rules, setRules] = useState<Rule[] | null>(null)
  const [history, setHistory] = useState<RuleEvent[]>([])
  const [confirming, setConfirming] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getRules().then(setRules).catch(() => setRules([]))
    getRuleHistory().then(setHistory).catch(() => setHistory([]))
  }, [])

  // Arriving from Insights' "View rule": bring that rule into view.
  useEffect(() => {
    if (rules && focus) document.getElementById(`rule-${focus}`)?.scrollIntoView({ block: 'center' })
  }, [rules, focus])

  async function act(fn: () => Promise<Rule[]>) {
    setBusy(true)
    setError(null)
    try {
      setRules(await fn())
      setConfirming(null)
      getRuleHistory().then(setHistory).catch(() => undefined)
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return false
    } finally {
      setBusy(false)
    }
  }

  if (!rules) return <p className="muted">Loading rules…</p>
  const reasons = config?.dismiss_reasons ?? {}

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Rules</h1>
          <p className="muted">What every ad is checked against. Changes apply to new checks only.</p>
        </div>
        {!adding && (
          <button className="btn primary" onClick={() => setAdding(true)}>
            Add rule
          </button>
        )}
      </div>

      {error && <p className="error">{error}</p>}
      {adding && (
        <RuleForm
          busy={busy}
          onCancel={() => setAdding(false)}
          onSubmit={async (rule) => {
            if (await act(() => createRule(rule))) setAdding(false)
          }}
        />
      )}

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
                <div
                  key={r.id}
                  id={`rule-${r.id}`}
                  className={`card rule${r.enabled ? '' : ' off'}${focus === r.id ? ' focused' : ''}`}
                >
                  <div className="rule-head">
                    <strong>
                      {r.name} {r.source === 'custom' && <span className="chip custom">Custom</span>}
                    </strong>
                    <label className="switch" title={r.enabled ? 'Switch off' : 'Switch on'}>
                      <input
                        type="checkbox"
                        checked={r.enabled}
                        disabled={busy}
                        onChange={(e) =>
                          // Switching on is safe; switching off asks first and records why.
                          e.target.checked ? act(() => toggleRule(r.id, true)) : setConfirming(r.id)
                        }
                      />
                      <span>{r.enabled ? 'On' : 'Off'}</span>
                    </label>
                  </div>
                  <span className="cite">{r.citation}</span>
                  <p>{r.description}</p>
                  {confirming === r.id && (
                    <SwitchOffConfirm
                      name={r.name}
                      builtin={r.source === 'builtin'}
                      busy={busy}
                      onCancel={() => setConfirming(null)}
                      onConfirm={(note) => act(() => toggleRule(r.id, false, note))}
                    />
                  )}
                  <div className="rule-foot">
                    <span className="muted small">{scope(r)}</span>
                    <Stats rule={r} reasons={reasons} />
                    {r.source === 'custom' && (
                      <button className="btn small ghost" disabled={busy} onClick={() => act(() => deleteRule(r.id))}>
                        Delete
                      </button>
                    )}
                  </div>
                </div>
              ))}
          </div>
        </section>
      ))}

      <section className="rule-section">
        <h2>Change history</h2>
        <div className="card activity">
          {history.length === 0 ? (
            <p className="muted small">No changes since the last reset.</p>
          ) : (
            <ol>
              {history.map((e) => (
                <li key={e.id}>
                  <span className={`dot dot-rule-${e.action}`} />
                  <div>
                    <strong>{e.actor}</strong> {HISTORY_TEXT[e.action]} “{e.rule_name}”
                    {e.note && <>: “{e.note}”</>}
                    <time title={clockTime(e.created_at)}>{timeAgo(e.created_at)}</time>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>
    </>
  )
}

const HISTORY_TEXT: Record<RuleEvent['action'], string> = {
  switched_on: 'switched on',
  switched_off: 'switched off',
  created: 'added',
  deleted: 'deleted',
}

function Checks<T extends string>({
  options,
  value,
  onChange,
}: {
  options: Record<T, string>
  value: T[]
  onChange: (v: T[]) => void
}) {
  return (
    <div className="checks">
      {(Object.entries(options) as [T, string][]).map(([key, label]) => (
        <label key={key} className="toggle">
          <input
            type="checkbox"
            checked={value.includes(key)}
            onChange={(e) => onChange(e.target.checked ? [...value, key] : value.filter((v) => v !== key))}
          />
          {label}
        </label>
      ))}
    </div>
  )
}

function RuleForm({
  busy,
  onCancel,
  onSubmit,
}: {
  busy: boolean
  onCancel: () => void
  onSubmit: (rule: NewRule) => void
}) {
  const [name, setName] = useState('')
  const [kind, setKind] = useState<NewRule['kind']>('phrases')
  const [phrases, setPhrases] = useState('')
  const [instruction, setInstruction] = useState('')
  const [products, setProducts] = useState<Product[]>([])
  const [channels, setChannels] = useState<Channel[]>([])

  const phraseList = phrases
    .split('\n')
    .map((p) => p.trim())
    .filter(Boolean)
  const ready = name.trim() && (kind === 'phrases' ? phraseList.length > 0 : instruction.trim().length >= 10)

  function submit(e: FormEvent) {
    e.preventDefault()
    if (ready) onSubmit({ name, kind, phrases: phraseList, instruction, products, channels })
  }

  return (
    <form className="card compose rule-form" onSubmit={submit}>
      <div className="eyebrow">New rule</div>
      <label>
        Name
        <input
          value={name}
          maxLength={80}
          placeholder="e.g. No “no credit check” claims"
          onChange={(e) => setName(e.target.value)}
        />
      </label>

      <fieldset className="kind">
        <legend>How should it be checked?</legend>
        <label className={`kind-option${kind === 'phrases' ? ' on' : ''}`}>
          <input type="radio" checked={kind === 'phrases'} onChange={() => setKind('phrases')} />
          <span>
            <b>
              <span className="badge check_failed inline">✕</span> Exact phrases
            </b>
            <small>Code flags any of these words, every time. Raises “check failed”.</small>
          </span>
        </label>
        <label className={`kind-option${kind === 'instruction' ? ' on' : ''}`}>
          <input type="radio" checked={kind === 'instruction'} onChange={() => setKind('instruction')} />
          <span>
            <b>
              <span className="badge needs_judgment inline">?</span> Plain-English rule
            </b>
            <small>The AI judges each ad against it. Raises “needs judgment”.</small>
          </span>
        </label>
      </fieldset>

      {kind === 'phrases' ? (
        <label>
          Phrases <span className="optional">one per line, case doesn't matter</span>
          <textarea
            rows={4}
            value={phrases}
            placeholder={'no credit check\nguaranteed approval'}
            onChange={(e) => setPhrases(e.target.value)}
          />
        </label>
      ) : (
        <label>
          Rule <span className="optional">{instruction.length}/500</span>
          <textarea
            rows={3}
            maxLength={500}
            value={instruction}
            placeholder="e.g. Implies that taking a loan will improve the reader's lifestyle or happiness."
            onChange={(e) => setInstruction(e.target.value)}
          />
        </label>
      )}

      <div className="row">
        <div>
          <span className="field-label">
            Products <span className="optional">none = all</span>
          </span>
          <Checks options={PRODUCTS} value={products} onChange={setProducts} />
        </div>
        <div>
          <span className="field-label">
            Channels <span className="optional">none = all</span>
          </span>
          <Checks options={CHANNELS} value={channels} onChange={setChannels} />
        </div>
      </div>

      <div className="form-actions">
        <button type="button" className="btn ghost" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn primary" disabled={busy || !ready}>
          Add rule
        </button>
      </div>
    </form>
  )
}
