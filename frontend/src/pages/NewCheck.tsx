import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { CHANNELS, createAsset, getLimits, PRODUCTS } from '../api'
import type { Channel, Limits, NewAsset, Product } from '../api'
import { EXAMPLES } from '../examples'
import { href } from '../router'

const EMPTY: NewAsset = { title: '', submitter: '', product: 'personal_loan', channel: 'landing_page', body: '', subject: '' }

// The subject only exists for email; blank optional fields are left to the server's defaults.
function toRequest(a: NewAsset): NewAsset {
  return {
    ...a,
    subject: a.channel === 'email' && a.subject?.trim() ? a.subject : null,
    title: a.title?.trim() || undefined,
    submitter: a.submitter?.trim() || undefined,
  }
}

export function NewCheck() {
  const [draft, setDraft] = useState<NewAsset>(EMPTY)
  const [limits, setLimits] = useState<Limits | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getLimits().then(setLimits).catch(() => setLimits(null))
  }, [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!draft.body.trim()) return
    setLoading(true)
    setError(null)
    try {
      const created = await createAsset(toRequest(draft))
      window.location.hash = href.review(created.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setLoading(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>New check</h1>
          <p className="muted">Paste marketing copy to check it before it goes live.</p>
        </div>
      </div>

      <div className="new-grid">
        <form className="card compose" onSubmit={submit}>
          <div className="row">
            <label>
              Product
              <select value={draft.product} onChange={(e) => setDraft({ ...draft, product: e.target.value as Product })}>
                {Object.entries(PRODUCTS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Channel
              <select value={draft.channel} onChange={(e) => setDraft({ ...draft, channel: e.target.value as Channel })}>
                {Object.entries(CHANNELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="row">
            <label>
              Title <span className="optional">optional</span>
              <input
                value={draft.title}
                maxLength={120}
                placeholder="e.g. Spring refinance email"
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              />
            </label>
            <label>
              Submitted by <span className="optional">optional</span>
              <input
                value={draft.submitter}
                maxLength={120}
                placeholder="e.g. HomeRate Partners (affiliate)"
                onChange={(e) => setDraft({ ...draft, submitter: e.target.value })}
              />
            </label>
          </div>
          {draft.channel === 'email' && (
            <label>
              Subject line
              <input
                value={draft.subject ?? ''}
                maxLength={500}
                onChange={(e) => setDraft({ ...draft, subject: e.target.value })}
              />
            </label>
          )}
          <label>
            Ad copy
            <textarea
              value={draft.body}
              rows={9}
              maxLength={20000}
              placeholder="Paste the ad, email or page text here."
              onChange={(e) => setDraft({ ...draft, body: e.target.value })}
            />
          </label>

          {error && <p className="error">{error}</p>}
          <div className="form-actions spread">
            <span className="muted small">
              {limits &&
                (limits.ai_enabled
                  ? `${limits.remaining_this_hour} of ${limits.limit_per_hour} AI checks left this hour`
                  : 'AI checks are off; code checks only')}
            </span>
            <button type="submit" className="btn primary" disabled={loading || !draft.body.trim()}>
              {loading ? 'Checking… (AI review takes a few seconds)' : 'Check ad'}
            </button>
          </div>
        </form>

        <aside className="card side-help">
          <div className="eyebrow">Try an example</div>
          <div className="example-list">
            {EXAMPLES.map((ex) => (
              <button
                key={ex.label}
                className="btn example"
                type="button"
                onClick={() => setDraft({ ...EMPTY, ...ex.asset, title: ex.label })}
              >
                {ex.label}
              </button>
            ))}
          </div>
          <div className="eyebrow">How flags work</div>
          <p className="small">
            <span className="badge check_failed inline">✕</span> <b>Check failed</b>: a definite violation, found by code.
          </p>
          <p className="small">
            <span className="badge needs_judgment inline">?</span> <b>Needs judgment</b>: a possible issue, found by AI.
          </p>
          <p className="muted small fineprint">Illustrative rules from public regulations. Not legal advice.</p>
        </aside>
      </div>
    </>
  )
}
