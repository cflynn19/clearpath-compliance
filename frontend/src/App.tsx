import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { analyze, CHANNELS, getLimits, PRODUCTS } from './api'
import type { AnalyzeResult, Asset, Channel, Limits, Product } from './api'
import { EXAMPLES } from './examples'
import { FlagList } from './FlagList'
import { Highlighted } from './Highlighted'

const EMPTY: Asset = { product: 'personal_loan', channel: 'landing_page', body: '', subject: '' }

// What gets sent: the subject only exists for email.
function toRequest(asset: Asset): Asset {
  return { ...asset, subject: asset.channel === 'email' && asset.subject?.trim() ? asset.subject : null }
}

function sameAsset(a: Asset, b: Asset) {
  const [x, y] = [toRequest(a), toRequest(b)]
  return x.body === y.body && x.product === y.product && x.channel === y.channel && x.subject === y.subject
}

function App() {
  const [draft, setDraft] = useState<Asset>(EMPTY)
  // The result and the exact asset it was computed for. Highlights are drawn on that
  // snapshot, so editing the draft never shifts them onto the wrong text.
  const [checked, setChecked] = useState<{ asset: Asset; result: AnalyzeResult } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [limits, setLimits] = useState<Limits | null>(null)
  const [active, setActive] = useState<number | null>(null)

  useEffect(() => {
    getLimits().then(setLimits).catch(() => setLimits(null))
  }, [])

  async function run(asset: Asset) {
    setLoading(true)
    setError(null)
    setActive(null)
    try {
      const result = await analyze(toRequest(asset))
      setChecked({ asset: toRequest(asset), result })
      setLimits({
        ai_enabled: result.ai.status !== 'disabled',
        remaining_this_hour: result.ai.remaining_this_hour,
        limit_per_hour: result.ai.limit_per_hour,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    if (draft.body.trim()) run(draft)
  }

  function select(flagIndex: number) {
    setActive(flagIndex)
    document.getElementById(`flag-${flagIndex}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    document.querySelector(`mark[data-flags~="${flagIndex}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }

  const edited = checked !== null && !sameAsset(draft, checked.asset)

  return (
    <div className="page">
      <header className="masthead">
        <h1>ClearPath Compliance Review</h1>
        <p>
          Paste marketing copy to check it before it goes live. Code finds definite rule violations; AI
          flags possible issues. You make every call.
        </p>
      </header>

      <main className="layout">
        <form className="panel compose" onSubmit={submit}>
          <div className="row">
            <label>
              Product
              <select
                value={draft.product}
                onChange={(e) => setDraft({ ...draft, product: e.target.value as Product })}
              >
                {Object.entries(PRODUCTS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Channel
              <select
                value={draft.channel}
                onChange={(e) => setDraft({ ...draft, channel: e.target.value as Channel })}
              >
                {Object.entries(CHANNELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
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
              rows={10}
              maxLength={20000}
              placeholder="Paste the ad, email or page text here."
              onChange={(e) => setDraft({ ...draft, body: e.target.value })}
            />
          </label>

          <div className="actions">
            <button type="submit" className="primary" disabled={loading || !draft.body.trim()}>
              {loading ? 'Checking…' : 'Check ad'}
            </button>
            {limits && (
              <span className="limit">
                {limits.ai_enabled
                  ? `${limits.remaining_this_hour} of ${limits.limit_per_hour} AI checks left this hour`
                  : 'AI checks are off; code checks only'}
              </span>
            )}
          </div>

          <div className="examples">
            <span>Try an example:</span>
            {EXAMPLES.map((ex) => (
              <button
                type="button"
                key={ex.label}
                disabled={loading}
                onClick={() => {
                  setDraft({ ...EMPTY, ...ex.asset })
                  run(ex.asset)
                }}
              >
                {ex.label}
              </button>
            ))}
          </div>
          <p className="fineprint">
            Rules are illustrative, based on public federal regulations (Reg Z, CAN-SPAM, UDAAP). Not legal
            advice. Re-checking unchanged text reuses the earlier result.
          </p>
        </form>

        <section className="panel results" aria-live="polite">
          {error && <p className="error">{error}</p>}
          {loading && <p className="status">Running code checks and AI review…</p>}
          {!loading && !checked && !error && (
            <p className="status">Results appear here: the ad with issues highlighted, and every flag explained.</p>
          )}

          {checked && !loading && (
            <>
              <p className={`ai ai-${checked.result.ai.status}`}>
                {checked.result.ai.message}
                {checked.result.ai.dropped > 0 &&
                  ` ${checked.result.ai.dropped} AI finding(s) discarded: their quotes weren't in the ad.`}
              </p>
              {edited && <p className="stale">You've edited the ad since this check. Check it again to update.</p>}

              <div className="copy">
                {checked.asset.subject && (
                  <p className="subject">
                    <span className="field">Subject:</span>{' '}
                    <Highlighted
                      text={checked.asset.subject}
                      field="subject"
                      flags={checked.result.flags}
                      active={active}
                      onSelect={select}
                    />
                  </p>
                )}
                <p className="body">
                  <Highlighted
                    text={checked.asset.body}
                    field="body"
                    flags={checked.result.flags}
                    active={active}
                    onSelect={select}
                  />
                </p>
              </div>

              <FlagList flags={checked.result.flags} active={active} onSelect={select} />
            </>
          )}
        </section>
      </main>
    </div>
  )
}

export default App
