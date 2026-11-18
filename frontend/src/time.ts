export const SLOT_MINUTES = 15

// "YYYY-MM-DD" for a date in the browser's local time
export function toDateInput(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

// Local midnight to next local midnight, as ISO strings with a UTC offset
export function dayRange(dateInput: string): { start: string; end: string } {
  const start = new Date(`${dateInput}T00:00`)
  const end = new Date(start)
  end.setDate(end.getDate() + 1)
  return { start: start.toISOString(), end: end.toISOString() }
}

// Minutes after local midnight of `dateInput` -> ISO string
export function minuteToIso(dateInput: string, minute: number): string {
  const date = new Date(`${dateInput}T00:00`)
  date.setMinutes(minute)
  return date.toISOString()
}

// ISO string -> minutes after local midnight of `dateInput`
export function isoToMinute(dateInput: string, iso: string): number {
  return (new Date(iso).getTime() - new Date(`${dateInput}T00:00`).getTime()) / 60000
}

// Today as "YYYY-MM-DD" (local)
export function todayInput(): string {
  return toDateInput(new Date())
}

export function isPast(iso: string): boolean {
  return new Date(iso).getTime() <= Date.now()
}

// "HH:MM" for a date in the browser's local time
export function toTimeInput(date: Date): string {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

// "YYYY-MM-DD" plus n calendar days
export function addDays(dateInput: string, days: number): string {
  const date = new Date(`${dateInput}T12:00`) // noon, so daylight saving changes can't shift the day
  date.setDate(date.getDate() + days)
  return toDateInput(date)
}

// e.g. "Thu, Nov 20"
export function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}
