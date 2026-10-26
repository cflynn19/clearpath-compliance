import type { Flag, FlagType, Span } from './api'
import { countHidden, stripHidden } from './hidden'


type HighlightFlag = Flag & { status?: string }

interface Mark {
  start: number
  end: number
  flagIndex: number
  type: FlagType
  resolved: boolean
}

interface Segment {
  text: string
  flags: number[]
  types: Set<FlagType> // of the open flags only; resolved ones fade
}

// Split the text at every highlight boundary, so overlapping highlights from different
// flags render as one piece of text carrying all of them.
function segment(text: string, marks: Mark[]): Segment[] {
  const cuts = new Set([0, text.length])
  for (const m of marks) {
    cuts.add(m.start)
    cuts.add(m.end)
  }
  const points = [...cuts].sort((a, b) => a - b)
  const segments: Segment[] = []
  for (let i = 0; i < points.length - 1; i++) {
    const [a, b] = [points[i], points[i + 1]]
    const covering = marks.filter((m) => m.start <= a && m.end >= b)
    segments.push({
      text: text.slice(a, b),
      flags: [...new Set(covering.map((m) => m.flagIndex))],
      types: new Set(covering.filter((m) => !m.resolved).map((m) => m.type)),
    })
  }
  return segments
}

// Invisible characters can't be highlighted, so they're shown as a visible marker.
function showHidden(text: string) {
  const count = countHidden(text)
  if (!count) return text
  return (
    <>
      {stripHidden(text)}
      <span className="hidden-chars">[{count} hidden]</span>
    </>
  )
}

export function Highlighted({
  text,
  field,
  flags,
  active,
  onSelect,
}: {
  text: string
  field: Span['field']
  flags: HighlightFlag[]
  active: number | null
  onSelect: (flagIndex: number) => void
}) {
  const marks: Mark[] = flags.flatMap((flag, flagIndex) =>
    flag.spans
      .filter((s) => s.field === field)
      .map((s) => ({
        start: s.start,
        end: s.end,
        flagIndex,
        type: flag.type,
        resolved: flag.status !== undefined && flag.status !== 'open',
      })),
  )

  return (
    <>
      {segment(text, marks).map((seg, i) => {
        if (!seg.flags.length) return <span key={i}>{seg.text}</span>
        const classes = ['hl', ...[...seg.types].map((t) => `hl-${t}`)]
        if (!seg.types.size) classes.push('hl-resolved')
        if (active !== null && seg.flags.includes(active)) classes.push('hl-active')
        return (
          <mark
            key={i}
            className={classes.join(' ')}
            data-flags={seg.flags.join(' ')}
            title={seg.flags.map((f) => flags[f].rule_name).join(' · ')}
            onClick={() => onSelect(seg.flags[0])}
          >
            {showHidden(seg.text)}
          </mark>
        )
      })}
    </>
  )
}
