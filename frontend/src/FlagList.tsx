import type { Flag, FlagType } from './api'
import { countHidden, stripHidden } from './hidden'

const TYPES: { type: FlagType; label: string; icon: string; hint: string }[] = [
  {
    type: 'check_failed',
    label: 'Check failed',
    icon: '✕',
    hint: 'Found by code. A yes/no fact: confirm it, then fix or dismiss.',
  },
  {
    type: 'needs_judgment',
    label: 'Needs judgment',
    icon: '?',
    hint: 'Found by AI. A possible issue: read it and decide.',
  },
]


function displayQuote(quote: string) {
  const hidden = countHidden(quote)
  const visible = stripHidden(quote)
  if (!hidden) return `“${quote}”`
  return visible ? `“${visible}” + ${hidden} hidden` : `${hidden} hidden character(s)`
}

export function FlagList({
  flags,
  active,
  onSelect,
}: {
  flags: Flag[]
  active: number | null
  onSelect: (flagIndex: number) => void
}) {
  if (!flags.length) {
    return <p className="empty">No flags. Nothing for a reviewer to check against these rules.</p>
  }

  return (
    <div className="flag-groups">
      {TYPES.map(({ type, label, icon, hint }) => {
        const group = flags.map((flag, i) => ({ flag, i })).filter(({ flag }) => flag.type === type)
        if (!group.length) return null
        return (
          <section key={type} className={`flag-group group-${type}`}>
            <h3>
              <span className={`type-badge type-${type}`} aria-hidden>
                {icon}
              </span>
              {label} <span className="count">{group.length}</span>
            </h3>
            <p className="hint">{hint}</p>
            <ul>
              {group.map(({ flag, i }) => (
                <li key={flag.rule_id}>
                  <button
                    id={`flag-${i}`}
                    className={`flag flag-${type}${active === i ? ' flag-active' : ''}`}
                    onClick={() => onSelect(i)}
                  >
                    <div className="flag-head">
                      <strong>{flag.rule_name}</strong>
                      {flag.spans.length > 1 && <span className="times">×{flag.spans.length}</span>}
                    </div>
                    <p className="why">{flag.why}</p>
                    {flag.spans.length > 0 ? (
                      <p className="quotes">
                        {flag.spans.map((s, j) => (
                          <q key={j} className={s.field === 'subject' ? 'in-subject' : undefined}>
                            {s.field === 'subject' && <span className="field">Subject: </span>}
                            {displayQuote(s.quote)}
                          </q>
                        ))}
                      </p>
                    ) : (
                      <p className="whole">Applies to the whole ad: something required is missing.</p>
                    )}
                    <p className="cite">{flag.citation}</p>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
