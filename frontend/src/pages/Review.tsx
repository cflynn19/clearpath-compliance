import { useEffect, useState } from 'react'
import { acknowledgeFlag, CHANNELS, decide, dismissFlag, getAsset, PRODUCTS, reopenFlag, STATUS_LABEL, submitRevision } from '../api'
import type { AssetDetail, Comparison, DecisionKind, FlagType, ReviewConfig, ReviewEvent, StoredFlag } from '../api'
import { clockTime, plural, shortReason, timeAgo } from '../format'
import { countHidden, stripHidden } from '../hidden'
import { Highlighted } from '../Highlighted'
import { href } from '../router'

const GROUPS: { type: FlagType; label: string; icon: string }[] = [
  { type: 'check_failed', label: 'Check failed', icon: '✕' },
  { type: 'needs_judgment', label: 'Needs judgment', icon: '?' },
]

function displayQuote(quote: string) {
  const hidden = countHidden(quote)
  const visible = stripHidden(quote)
  if (!hidden) return `“${quote}”`
  return visible ? `“${visible}” + ${hidden} hidden` : `${hidden} hidden character(s)`
}

export function Review({ id, config, onChange }: { id: number; config: ReviewConfig; onChange: () => void }) {
  const [asset, setAsset] = useState<AssetDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [active, setActive] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)

  // App remounts this page per ad (key={id}), so state starts fresh for each one.
  useEffect(() => {
    getAsset(id)
      .then(setAsset)
      .catch((e) => setError(e.message))
  }, [id])

  async function act(fn: () => Promise<AssetDetail>) {
    setBusy(true)
    setError(null)
    try {
      setAsset(await fn())
      onChange()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  function select(i: number) {
    setActive(i)
    document.getElementById(`flag-${i}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }

  if (error && !asset) return <p className="error">{error}</p>
  if (!asset) return <p className="muted">Loading…</p>

  const open = asset.flags.filter((f) => f.status === 'open')
  const openFailed = open.filter((f) => f.type === 'check_failed').length
  const openJudgment = open.length - openFailed
  const resolved = asset.flags.length - open.length
  const deciding = asset.status === 'in_review'
  const ai = asset.version.ai

  return (
    <div className={deciding ? 'with-decision-bar' : ''}>
      <div className="crumbs">
        <a href={href.queue}>Queue</a> <span>/</span> {asset.title}
      </div>

      <div className="titlebar">
        <div>
          <h1>{asset.title}</h1>
          <div className="meta">
            <span className="tag">{PRODUCTS[asset.product]}</span>
            <span className="tag">{CHANNELS[asset.channel]}</span>
            <span className="muted">
              {asset.submitter} · Version {asset.version.number} · Submitted {timeAgo(asset.created_at)}
            </span>
          </div>
        </div>
        <span className={`state state-${asset.status}`}>{STATUS_LABEL[asset.status]}</span>
      </div>

      <Verdict asset={asset} openFailed={openFailed} openJudgment={openJudgment} resolved={resolved} />

      {asset.comparison && <ComparisonBanner c={asset.comparison} />}
      {asset.status === 'needs_changes' && (
        <RevisePanel asset={asset} busy={busy} onSubmit={(body, subject) => act(() => submitRevision(asset.id, body, subject))} />
      )}
      {ai.status !== 'ran' && ai.status !== 'cached' && <p className="notice">{ai.message}</p>}
      {ai.dropped > 0 && (
        <p className="notice subtle">
          {plural(ai.dropped, 'AI finding')} discarded because the quoted text wasn't in the ad.
        </p>
      )}
      {error && <p className="error">{error}</p>}

      <div className="review-grid">
        <div className="left-col">
          <article className="card doc">
            <div className="eyebrow">Ad copy</div>
            {asset.version.subject && (
              <p className="subject">
                <span className="label">Subject</span>
                <Highlighted
                  text={asset.version.subject}
                  field="subject"
                  flags={asset.flags}
                  active={active}
                  onSelect={select}
                />
              </p>
            )}
            <p className="body">
              <Highlighted text={asset.version.body} field="body" flags={asset.flags} active={active} onSelect={select} />
            </p>
            <div className="legend">
              <span>
                <i className="key fail" /> Check failed: a definite rule violation
              </span>
              <span>
                <i className="key judge" /> Needs judgment: a possible issue
              </span>
            </div>
          </article>
          <Activity events={asset.events} reasons={config.dismiss_reasons} />
        </div>

        <aside className="flags">
          {asset.flags.length === 0 && (
            <div className="card empty-state">
              <strong>No flags</strong>
              <p className="muted">Nothing in this ad matched the rules. It's ready for your decision.</p>
            </div>
          )}
          {GROUPS.map((g) => {
            // The legend under the ad explains the two types, so the groups don't repeat it.
            const group = asset.flags.map((f, i) => ({ f, i })).filter(({ f }) => f.type === g.type)
            if (!group.length) return null
            const openCount = group.filter(({ f }) => f.status === 'open').length
            return (
              <section key={g.type} className="flag-group">
                <h2>
                  <span className={`badge ${g.type}`}>{g.icon}</span> {g.label}
                  <em>{openCount ? `${openCount} open` : 'all resolved'}</em>
                </h2>
                {group.map(({ f, i }) => (
                  <FlagCard
                    key={f.id}
                    flag={f}
                    index={i}
                    active={active === i}
                    editable={deciding}
                    busy={busy}
                    reasons={config.dismiss_reasons}
                    onSelect={() => setActive(i)}
                    onDismiss={(reason, note) => act(() => dismissFlag(f.id, reason, note))}
                    onAcknowledge={() => act(() => acknowledgeFlag(f.id))}
                    onReopen={() => act(() => reopenFlag(f.id))}
                  />
                ))}
              </section>
            )
          })}
        </aside>
      </div>

      {deciding && (
        <DecisionBar
          openCount={open.length}
          busy={busy}
          onDecide={(decision, note) => act(() => decide(asset.id, decision, note))}
        />
      )}
    </div>
  )
}

function Verdict({
  asset,
  openFailed,
  openJudgment,
  resolved,
}: {
  asset: AssetDetail
  openFailed: number
  openJudgment: number
  resolved: number
}) {
  const total = asset.flags.length
  let tone: 'bad' | 'good' | 'done-bad' | 'pending'
  let title: string
  let detail: string

  if (asset.status === 'approved') {
    tone = 'good'
    title = 'Approved'
    detail = `by ${asset.decided_by} at ${clockTime(asset.decided_at!)}`
  } else if (asset.status === 'rejected') {
    tone = 'done-bad'
    title = 'Rejected'
    detail = `by ${asset.decided_by} at ${clockTime(asset.decided_at!)}${asset.decision_note ? `: “${asset.decision_note}”` : ''}`
  } else if (asset.status === 'needs_changes') {
    tone = 'pending'
    title = 'Changes requested'
    const ev = asset.events.find((e) => e.action === 'changes_requested')
    const note = ev?.detail.note as string | null | undefined
    detail = `Waiting on ${asset.submitter} for a revised version${note ? `: “${note}”` : '.'}`
  } else if (openFailed + openJudgment > 0) {
    tone = 'bad'
    title = 'Not ready to approve'
    detail = [
      openFailed && `${plural(openFailed, 'check')} failed`,
      openJudgment && `${openJudgment} need${openJudgment === 1 ? 's' : ''} your judgment`,
      resolved && `${resolved} resolved`,
    ]
      .filter(Boolean)
      .join(' · ')
  } else {
    tone = 'good'
    title = 'Ready for your decision'
    detail = total ? `All ${plural(total, 'flag')} resolved.` : 'No flags raised.'
  }

  return (
    <section className={`card verdict verdict-${tone}`}>
      <div className="verdict-main">
        <span className="verdict-icon">{tone === 'bad' ? '!' : tone === 'good' ? '✓' : tone === 'pending' ? '↺' : '✕'}</span>
        <div>
          <strong>{title}</strong>
          <span>{detail}</span>
        </div>
      </div>
      {total > 0 && (
        <div className="progress">
          <span>
            {resolved} of {total} resolved
          </span>
          <div className="bar">
            <i style={{ width: `${(resolved / total) * 100}%` }} />
          </div>
        </div>
      )}
    </section>
  )
}

function FlagCard({
  flag,
  index,
  active,
  editable,
  busy,
  reasons,
  onSelect,
  onDismiss,
  onAcknowledge,
  onReopen,
}: {
  flag: StoredFlag
  index: number
  active: boolean
  editable: boolean
  busy: boolean
  reasons: Record<string, string>
  onSelect: () => void
  onDismiss: (reason: string, note: string) => void
  onAcknowledge: () => void
  onReopen: () => void
}) {
  const [dismissing, setDismissing] = useState(false)
  const isOpen = flag.status === 'open'

  return (
    <div
      id={`flag-${index}`}
      className={`card flag ${flag.type}${active ? ' active' : ''}${isOpen ? '' : ' resolved'}`}
      onClick={onSelect}
    >
      <div className="flag-top">
        <strong>{flag.rule_name}</strong>
        {flag.spans.length > 1 && <span className="chip">×{flag.spans.length}</span>}
        {flag.spans.length === 0 && <span className="chip">Whole ad</span>}
        {flag.status === 'dismissed' && <span className="chip done">Dismissed</span>}
        {flag.status === 'acknowledged' && <span className="chip done">Acknowledged</span>}
        {flag.carried_over && (
          <span className="chip" title="Resolved on the previous version; same rule, same text, so it carried over">
            Carried over
          </span>
        )}
      </div>
      <p>{flag.why}</p>
      {flag.spans.some((s) => s.field === 'subject' || countHidden(s.quote)) && (
        <p className="quotes">
          {flag.spans.map((s, j) => (
            <q key={j}>
              {s.field === 'subject' && <span className="label">Subject </span>}
              {displayQuote(s.quote)}
            </q>
          ))}
        </p>
      )}
      {!isOpen && (
        <p className="resolution">
          {flag.status === 'dismissed' ? shortReason(reasons, flag.reason) : 'Acknowledged'}
          {flag.note && <>: “{flag.note}”</>} — {flag.resolved_by}, {clockTime(flag.resolved_at!)}
        </p>
      )}

      {dismissing ? (
        <DismissForm
          reasons={reasons}
          busy={busy}
          onCancel={() => setDismissing(false)}
          onSubmit={(reason, note) => {
            onDismiss(reason, note)
            setDismissing(false)
          }}
        />
      ) : (
        <div className="flag-foot">
          <span className="cite">{flag.citation}</span>
          {editable && (
            <span className="actions" onClick={(e) => e.stopPropagation()}>
              {isOpen ? (
                <>
                  <button className="btn small" disabled={busy} onClick={() => setDismissing(true)}>
                    Dismiss…
                  </button>
                  {flag.type === 'needs_judgment' && (
                    <button className="btn small soft" disabled={busy} onClick={onAcknowledge}>
                      Acknowledge
                    </button>
                  )}
                </>
              ) : (
                <button className="btn small ghost" disabled={busy} onClick={onReopen}>
                  Undo
                </button>
              )}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function DismissForm({
  reasons,
  busy,
  onCancel,
  onSubmit,
}: {
  reasons: Record<string, string>
  busy: boolean
  onCancel: () => void
  onSubmit: (reason: string, note: string) => void
}) {
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const needsNote = reason === 'other' && !note.trim()

  return (
    <form
      className="dismiss-form"
      onClick={(e) => e.stopPropagation()}
      onSubmit={(e) => {
        e.preventDefault()
        if (reason && !needsNote) onSubmit(reason, note)
      }}
    >
      <fieldset>
        <legend>Why dismiss this flag?</legend>
        {Object.entries(reasons).map(([key, label]) => (
          <label key={key} className="radio">
            <input type="radio" name="reason" value={key} checked={reason === key} onChange={() => setReason(key)} />
            {label}
          </label>
        ))}
      </fieldset>
      <textarea
        rows={2}
        maxLength={1000}
        placeholder={reason === 'other' ? 'Required: explain why' : 'Optional note for the audit trail'}
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <div className="form-actions">
        <button type="button" className="btn small ghost" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn small primary" disabled={busy || !reason || needsNote}>
          Dismiss flag
        </button>
      </div>
    </form>
  )
}

function DecisionBar({
  openCount,
  busy,
  onDecide,
}: {
  openCount: number
  busy: boolean
  onDecide: (decision: DecisionKind, note: string) => void
}) {
  // Reject and request changes both take an optional note before confirming.
  const [pending, setPending] = useState<'reject' | 'request_changes' | null>(null)
  const [note, setNote] = useState('')

  return (
    <footer className="decision-bar">
      {pending ? (
        <>
          <input
            autoFocus
            maxLength={1000}
            placeholder={
              pending === 'reject'
                ? 'Reason for rejecting (optional, goes to the audit trail)'
                : 'Note for the submitter (optional: the open flags are already the list of fixes)'
            }
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="decision-actions">
            <button className="btn ghost" onClick={() => setPending(null)}>
              Cancel
            </button>
            <button
              className={`btn ${pending === 'reject' ? 'danger' : 'primary'}`}
              disabled={busy}
              onClick={() => onDecide(pending, note)}
            >
              {pending === 'reject' ? 'Confirm reject' : 'Send back for changes'}
            </button>
          </div>
        </>
      ) : (
        <>
          <span className="hint">
            {openCount
              ? `Resolve the ${plural(openCount, 'open flag')} to approve, or send it back for changes.`
              : 'Every flag is resolved. Approve, or reject if it still isn’t right.'}
          </span>
          <div className="decision-actions">
            <button className="btn outline-danger" disabled={busy} onClick={() => setPending('reject')}>
              Reject
            </button>
            {openCount > 0 && (
              <button className="btn soft" disabled={busy} onClick={() => setPending('request_changes')}>
                Request changes
              </button>
            )}
            <button className="btn primary" disabled={busy || openCount > 0} onClick={() => onDecide('approve', '')}>
              Approve
            </button>
          </div>
        </>
      )}
    </footer>
  )
}

const ACTION_TEXT: Record<string, string> = {
  submitted: 'submitted the ad',
  checked: 'ran the checks',
  flag_dismissed: 'dismissed',
  flag_acknowledged: 'acknowledged',
  flag_reopened: 'reopened',
  approved: 'approved the ad',
  rejected: 'rejected the ad',
  changes_requested: 'requested changes',
  revised: 'submitted a revised version',
}

function describe(e: ReviewEvent, reasons: Record<string, string>) {
  const d = e.detail as Record<string, string | number | null>
  if (e.action === 'checked') {
    return `${ACTION_TEXT.checked}: ${d.check_failed} failed, ${d.needs_judgment} to judge (AI ${d.ai})`
  }
  if (e.action.startsWith('flag_')) {
    const reason = d.reason ? ` as ${shortReason(reasons, d.reason as string).toLowerCase()}` : ''
    return `${ACTION_TEXT[e.action]} “${d.rule}”${reason}${d.note ? `: “${d.note}”` : ''}`
  }
  if (e.action === 'revised') {
    const c = e.detail as unknown as Comparison
    return `${ACTION_TEXT.revised} (v${c.version}): ${c.fixed.length} fixed, ${c.still_flagged.length} still flagged, ${c.new.length} new, ${c.carried_over} carried over`
  }
  if (e.action === 'changes_requested') {
    return `${ACTION_TEXT.changes_requested} (${plural(Number(d.open_flags), 'open flag')})${d.note ? `: “${d.note}”` : ''}`
  }
  return `${ACTION_TEXT[e.action] ?? e.action}${d.note ? `: “${d.note}”` : ''}`
}

function ComparisonBanner({ c }: { c: Comparison }) {
  const part = (n: number, label: string, names: string[], tone: string) =>
    n > 0 && (
      <span className={`cmp ${tone}`} title={names.join(' · ')}>
        {n} {label}
      </span>
    )
  return (
    <section className="card comparison">
      <span className="eyebrow">Since version {c.version - 1}</span>
      <div className="cmp-row">
        {part(c.fixed.length, 'fixed', c.fixed, 'ok')}
        {part(c.still_flagged.length, 'still flagged', c.still_flagged, 'judge')}
        {part(c.new.length, 'new', c.new, 'fail')}
        {part(c.carried_over, 'carried over', [], 'muted')}
        {!c.fixed.length && !c.still_flagged.length && !c.new.length && !c.carried_over && (
          <span className="cmp muted">No change in flags</span>
        )}
      </div>
    </section>
  )
}

// There's no submitter portal in v1 (A6), so the submitter's corrected copy is entered here.
function RevisePanel({
  asset,
  busy,
  onSubmit,
}: {
  asset: AssetDetail
  busy: boolean
  onSubmit: (body: string, subject: string | null) => void
}) {
  const [body, setBody] = useState(asset.version.body)
  const [subject, setSubject] = useState(asset.version.subject ?? '')
  const isEmail = asset.channel === 'email'
  const changed = body !== asset.version.body || (isEmail && subject !== (asset.version.subject ?? ''))
  return (
    <section className="card revise">
      <div className="eyebrow">Submit a revised version · as {asset.submitter}</div>
      {isEmail && <input value={subject} maxLength={500} onChange={(e) => setSubject(e.target.value)} />}
      <textarea rows={6} maxLength={20000} value={body} onChange={(e) => setBody(e.target.value)} />
      <div className="form-actions">
        <button
          className="btn primary"
          disabled={busy || !body.trim() || !changed}
          onClick={() => onSubmit(body, isEmail && subject.trim() ? subject : null)}
        >
          {busy ? 'Checking…' : 'Submit version ' + (asset.version.number + 1)}
        </button>
      </div>
    </section>
  )
}

function Activity({ events, reasons }: { events: ReviewEvent[]; reasons: Record<string, string> }) {
  return (
    <section className="card activity">
      <div className="eyebrow">Audit trail</div>
      <ol>
        {events.map((e) => (
          <li key={e.id}>
            <span className={`dot dot-${e.action}`} />
            <div>
              <strong>{e.actor}</strong> {describe(e, reasons)}
              <time>{clockTime(e.created_at)}</time>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
