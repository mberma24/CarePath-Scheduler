// All dates and times in the UI are in the clinic's timezone (CLINIC_TIMEZONE from GET /config),
// whatever timezone the browser is in. The API always uses UTC ISO strings.

// Set from GET /config by App before any tab renders (`export let` is a live binding,
// so every importer sees the updated value)
export let SLOT_MINUTES = 15
let clinicTimeZone = 'America/New_York'

export function applyClinicSettings(timeZone: string, slotMinutes: number): void {
  clinicTimeZone = timeZone
  SLOT_MINUTES = slotMinutes
}

interface WallTime {
  year: number
  month: number // 1-12
  day: number
  hour: number
  minute: number
  second: number
}

// The clinic's wall-clock date and time at an instant
function wallTime(date: Date): WallTime {
  const format = new Intl.DateTimeFormat('en-US', {
    timeZone: clinicTimeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
  const parts = Object.fromEntries(format.formatToParts(date).map((p) => [p.type, Number(p.value)]))
  return {
    year: parts.year,
    month: parts.month,
    day: parts.day,
    hour: parts.hour,
    minute: parts.minute,
    second: parts.second,
  }
}

// How far the clinic's clock is ahead of UTC at an instant, in ms (e.g. -5h in New York winter)
function clinicOffset(date: Date): number {
  const w = wallTime(date)
  const asUtc = Date.UTC(w.year, w.month - 1, w.day, w.hour, w.minute, w.second)
  return asUtc - Math.floor(date.getTime() / 1000) * 1000
}

// Clinic wall-clock time -> the real instant. `minute` may exceed a day (it rolls over).
// Two passes, so a time just after a daylight saving change uses the right offset.
function fromWallTime(dateInput: string, minute: number): Date {
  const [year, month, day] = dateInput.split('-').map(Number)
  const wall = Date.UTC(year, month - 1, day, 0, minute)
  const first = wall - clinicOffset(new Date(wall))
  return new Date(wall - clinicOffset(new Date(first)))
}

const pad = (n: number) => String(n).padStart(2, '0')

// "YYYY-MM-DD" of the clinic day an instant falls on
export function toDateInput(date: Date): string {
  const w = wallTime(date)
  return `${w.year}-${pad(w.month)}-${pad(w.day)}`
}

// "HH:MM" clinic time of an instant
export function toTimeInput(date: Date): string {
  const w = wallTime(date)
  return `${pad(w.hour)}:${pad(w.minute)}`
}

// Today in the clinic, as "YYYY-MM-DD"
export function todayInput(): string {
  return toDateInput(new Date())
}

// The current clinic time, as "HH:MM"
export function nowTimeInput(): string {
  return toTimeInput(new Date())
}

// "YYYY-MM-DD" plus n calendar days (pure date arithmetic, no timezone involved)
export function addDays(dateInput: string, days: number): string {
  const [year, month, day] = dateInput.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day + days))
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`
}

// Clinic midnight to the next clinic midnight, as UTC ISO strings
export function dayRange(dateInput: string): { start: string; end: string } {
  return {
    start: fromWallTime(dateInput, 0).toISOString(),
    end: fromWallTime(addDays(dateInput, 1), 0).toISOString(),
  }
}

// A clinic date and "HH:MM" -> the real instant
export function clinicDateTime(dateInput: string, timeInput: string): Date {
  const [hour, minute] = (timeInput || '00:00').split(':').map(Number)
  return fromWallTime(dateInput, hour * 60 + minute)
}

// Minutes after clinic midnight of `dateInput` (wall clock) -> UTC ISO string
export function minuteToIso(dateInput: string, minute: number): string {
  return fromWallTime(dateInput, minute).toISOString()
}

// UTC ISO string -> wall-clock minutes after clinic midnight of `dateInput`.
// Wall-clock (not elapsed) minutes, so 7:00 is always 420, even on daylight saving days.
export function isoToMinute(dateInput: string, iso: string): number {
  const w = wallTime(new Date(iso))
  const [year, month, day] = dateInput.split('-').map(Number)
  const dayDiff = (Date.UTC(w.year, w.month - 1, w.day) - Date.UTC(year, month - 1, day)) / 86_400_000
  return dayDiff * 24 * 60 + w.hour * 60 + w.minute + w.second / 60
}

export function isPast(iso: string): boolean {
  return new Date(iso).getTime() <= Date.now()
}

// e.g. "Thu, Nov 20", in clinic time
export function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString([], {
    timeZone: clinicTimeZone,
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

// e.g. "9:15 AM", in clinic time
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    timeZone: clinicTimeZone,
    hour: 'numeric',
    minute: '2-digit',
  })
}
