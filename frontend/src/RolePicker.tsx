import { useEffect, useRef, useState } from 'react'
import type { Patient, Resource } from './types'

interface Props {
  value: string // "admin", "patient:3", or "resource:5"
  patients: Patient[]
  resources: Resource[]
  onChange: (value: string) => void
  onOpen: () => void // lets the parent reload names
}

interface Option {
  value: string
  name: string
  detail: string // shown on the right, and searchable
  group: string
}

// "Viewing as" dropdown with a search box; the list scrolls when there are many people
export default function RolePicker({ value, patients, resources, onChange, onOpen }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  const options: Option[] = [
    { value: 'admin', name: 'Admin', detail: '', group: '' },
    ...patients.map((p) => ({ value: `patient:${p.id}`, name: p.name, detail: 'patient', group: 'Patients' })),
    ...resources.map((r) => ({ value: `resource:${r.id}`, name: r.name, detail: r.type, group: 'Staff & equipment' })),
  ]
  const current = options.find((o) => o.value === value)
  const q = query.trim().toLowerCase()
  const visible = options.filter((o) => o.name.toLowerCase().includes(q) || o.detail.toLowerCase().includes(q))

  // Close on a click outside or Esc
  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  function toggle() {
    if (!open) {
      onOpen()
      setQuery('')
    }
    setOpen(!open)
  }

  function pick(option: Option) {
    onChange(option.value)
    setOpen(false)
  }

  return (
    <div className="role-picker" ref={ref}>
      <span title="Demo role switcher, not real login. The API doesn't check roles.">Viewing as</span>
      <button className="role-button" onClick={toggle}>
        {current?.name ?? 'Admin'} <span className="muted">⌄</span>
      </button>

      {open && (
        <div className="role-menu">
          <input
            className="full"
            autoFocus
            placeholder="Search people…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="list">
            {visible.map((o, i) => (
              <div key={o.value}>
                {o.group && o.group !== visible[i - 1]?.group && <div className="label role-group">{o.group}</div>}
                <button className={o.value === value ? 'list-item active' : 'list-item'} onClick={() => pick(o)}>
                  <span>{o.name}</span>
                  <span className="muted">{o.detail}</span>
                </button>
              </div>
            ))}
            {visible.length === 0 && <p className="muted" style={{ padding: 8, margin: 0 }}>No matches.</p>}
          </div>
        </div>
      )}
    </div>
  )
}
