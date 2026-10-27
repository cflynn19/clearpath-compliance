import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

export interface MenuItem {
  label: string
  icon: ReactNode
  href?: string
  onSelect?: () => void
  danger?: boolean
}

// A "⋯" row-actions menu: labelled items, closes on outside click or Escape.
export function RowMenu({ label, items }: { label: string; items: MenuItem[] }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const safe = items.filter((i) => !i.danger)
  const danger = items.filter((i) => i.danger)

  const render = (item: MenuItem) =>
    item.href ? (
      <a key={item.label} role="menuitem" href={item.href} onClick={() => setOpen(false)}>
        {item.icon}
        {item.label}
      </a>
    ) : (
      <button
        key={item.label}
        role="menuitem"
        className={item.danger ? 'danger' : ''}
        onClick={() => {
          setOpen(false)
          item.onSelect?.()
        }}
      >
        {item.icon}
        {item.label}
      </button>
    )

  return (
    <div className="row-menu" ref={ref}>
      <button
        className="icon-btn"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <circle cx="5" cy="12" r="2" />
          <circle cx="12" cy="12" r="2" />
          <circle cx="19" cy="12" r="2" />
        </svg>
      </button>
      {open && (
        <div className="menu" role="menu">
          {safe.map(render)}
          {danger.length > 0 && <hr />}
          {danger.map(render)}
        </div>
      )}
    </div>
  )
}
