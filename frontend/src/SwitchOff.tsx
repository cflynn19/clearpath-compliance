import { useState } from 'react'

// Switching a rule off is a compliance decision, so it asks first: more firmly for a
// built-in regulatory rule. The optional reason goes into the rule change history.
export function SwitchOffConfirm({
  name,
  builtin,
  busy,
  onConfirm,
  onCancel,
}: {
  name: string
  builtin: boolean
  busy: boolean
  onConfirm: (note: string) => void
  onCancel: () => void
}) {
  const [note, setNote] = useState('')
  return (
    <div className="confirm" onClick={(e) => e.stopPropagation()}>
      <p>
        {builtin ? (
          <>
            <b>“{name}” is a regulatory rule.</b> Switched off, no new ad is checked for it. Ads already checked keep
            their flags.
          </>
        ) : (
          <>
            Switch off <b>“{name}”</b> for new checks?
          </>
        )}
      </p>
      <input
        autoFocus
        maxLength={500}
        placeholder="Why? (saved to the rule change history)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <div className="form-actions">
        <button className="btn small ghost" onClick={onCancel}>
          Cancel
        </button>
        <button className="btn small danger" disabled={busy} onClick={() => onConfirm(note)}>
          Switch off
        </button>
      </div>
    </div>
  )
}
