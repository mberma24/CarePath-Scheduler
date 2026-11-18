import { useLayoutEffect, useRef, type ReactNode } from 'react'
import { SLOT_MINUTES, formatTime, isPast, isoToMinute, minuteToIso } from './time'

export interface TimelineItem {
  id: number | string
  start: string
  end: string
  label: ReactNode
  className: string
}

interface Props {
  date: string // "YYYY-MM-DD", local
  items: TimelineItem[]
  selection?: { start: number; end: number } | null // minutes after midnight
  onSlotPress?: (minute: number) => void // mouse pressed on a row
  onSlotEnter?: (minute: number) => void // mouse moved onto a row
  fit?: boolean // only show the hours the items cover
  lockPast?: boolean // rows that have already ended are greyed out and can't be selected
  hours?: [number, number] // otherwise show these hours (default: the whole day)
}

const ROW_PX = 20 // must match .timeline-row height

// A vertical day view, one row per slot (SLOT_MINUTES). Shows `hours` (default the whole day), or with
// `fit` only the hours the items cover.
export default function Timeline({
  date,
  items,
  selection,
  onSlotPress,
  onSlotEnter,
  fit = false,
  hours = [0, 24],
  lockPast = false,
}: Props) {
  let first = hours[0] * 60
  let last = hours[1] * 60
  if (fit && items.length) {
    first = Math.min(...items.map((item) => Math.floor(isoToMinute(date, item.start) / 60) * 60))
    last = Math.max(...items.map((item) => Math.ceil(isoToMinute(date, item.end) / 60) * 60))
    first = Math.max(0, first)
    last = Math.min(24 * 60, last)
  }

  const slots: number[] = []
  for (let m = first; m < last; m += SLOT_MINUTES) slots.push(m)
  const top = (minute: number) => ((minute - first) / SLOT_MINUTES) * ROW_PX

  // Keep the timeline above the bottom of the window; it scrolls inside instead
  const scrollRef = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const resize = () => {
      el.style.maxHeight = `${Math.max(200, window.innerHeight - el.getBoundingClientRect().top - 32)}px`
    }
    resize()
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [])

  // When the day changes, start the view at 7:00 (or the top, when fitted)
  useLayoutEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = fit ? 0 : ((7 * 60 - first) / SLOT_MINUTES) * ROW_PX
  }, [date, first, fit])

  return (
    <div className="timeline-scroll" ref={scrollRef}>
    <div className="timeline">
      {slots.map((m) => {
        const past = lockPast && isPast(minuteToIso(date, m + SLOT_MINUTES))
        const classes = ['timeline-row']
        if (m % 60 === 0) classes.push('hour')
        if (past) classes.push('past')
        else if (onSlotPress) classes.push('clickable')
        if (selection && m >= selection.start && m < selection.end) classes.push('selected')
        return (
          <div
            key={m}
            className={classes.join(' ')}
            onMouseDown={past ? undefined : onSlotPress && (() => onSlotPress(m))}
            onMouseEnter={past ? undefined : onSlotEnter && (() => onSlotEnter(m))}
          >
            {m % 60 === 0 && <span className="timeline-label">{formatTime(minuteToIso(date, m))}</span>}
          </div>
        )
      })}

      {items.map((item) => {
        const start = Math.max(first, isoToMinute(date, item.start))
        const end = Math.min(last, isoToMinute(date, item.end))
        if (end <= start) return null
        return (
          <div
            key={item.id}
            className={`timeline-item ${item.className}`}
            style={{ top: top(start), height: top(end) - top(start) }}
          >
            {item.label}
          </div>
        )
      })}
    </div>
    </div>
  )
}
