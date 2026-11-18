import { useEffect, useState } from 'react'
import * as api from './api'
import Timeline from './Timeline'
import { SLOT_MINUTES, addDays, clinicDateTime, dayRange, formatDay, formatTime, isPast, nowTimeInput, toDateInput, todayInput, toTimeInput } from './time'
import type { Config, CarePath, Patient, Resource, ScheduleResponse } from './types'

interface Props {
  config: Config // clinic hours and search horizon from GET /config
  lockedPatientId?: number // a patient is viewing (demo roles), so they can only search for themselves
}

export default function FindTab({ config, lockedPatientId }: Props) {
  const [carePaths, setCarePaths] = useState<CarePath[]>([])
  const [patients, setPatients] = useState<Patient[]>([])
  const [resources, setResources] = useState<Resource[]>([])
  const [carePathId, setCarePathId] = useState('')
  const [patientId, setPatientId] = useState(lockedPatientId ? String(lockedPatientId) : '')
  const [result, setResult] = useState<ScheduleResponse | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [date, setDate] = useState(() => toDateInput(new Date()))
  const [time, setTime] = useState(() => toTimeInput(new Date()))
  const [searchedNext, setSearchedNext] = useState(false)
  const [booked, setBooked] = useState(false)

  useEffect(() => {
    Promise.all([api.listCarePaths(), api.listPatients(), api.listResources()])
      .then(([k, p, r]) => {
        setCarePaths(k)
        setPatients(p)
        setResources(r)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  // Search from the chosen date/time (never before now) through the last day of the horizon,
  // counted in calendar days: a 7-day horizon from Nov 18 searches Nov 18-24.
  // The backend keeps every appointment inside clinic hours.
  const chosenStart = clinicDateTime(date, time)
  const lastDay = addDays(date, config.schedule_horizon_days - 1)
  const searchEnd = dayRange(lastDay).end
  const dayOver = isPast(searchEnd)
  const dayMinutes = (config.clinic_close_hour - config.clinic_open_hour) * 60

  const carePath = carePaths.find((k) => String(k.id) === carePathId)
  const tooLong = carePath !== undefined && carePath.total_minutes > dayMinutes
  const noSteps = carePath !== undefined && carePath.steps.length === 0

  const resourceName = (id: number | null) =>
    id === null ? '' : (resources.find((r) => r.id === id)?.name ?? `#${id}`)

  // `next`: search again starting one slot after the current result's start
  async function find(next = false) {
    const start =
      next && result?.start_time
        ? new Date(new Date(result.start_time).getTime() + SLOT_MINUTES * 60_000)
        : chosenStart
    setError('')
    setResult(null)
    setBooked(false)
    setSearchedNext(next)
    setLoading(true)
    try {
      setResult(await api.findSchedule(Number(carePathId), Number(patientId), start.toISOString(), searchEnd))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  async function book() {
    if (!result?.start_time) return
    setError('')
    setLoading(true)
    try {
      // Show what was actually booked (the care path may have changed since the search)
      setResult(await api.bookSchedule(Number(carePathId), Number(patientId), result.start_time))
      setBooked(true)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="split">
      <div className="panel stack">
        <h2>Find earliest schedule</h2>
        <select
          className="full"
          value={carePathId}
          onChange={(e) => {
            setCarePathId(e.target.value)
            setResult(null)
          }}
        >
          <option value="">Choose a care path…</option>
          {carePaths.map((k) => (
            <option key={k.id} value={k.id}>
              {k.name} ({k.total_minutes} min)
            </option>
          ))}
        </select>
        <select
          className="full"
          value={patientId}
          disabled={lockedPatientId !== undefined}
          onChange={(e) => {
            setPatientId(e.target.value)
            setResult(null)
          }}
        >
          <option value="">Choose a patient…</option>
          {patients.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <div className="row">
          <input
            type="date"
            style={{ flex: 1, minWidth: 0 }}
            min={todayInput()}
            value={date}
            onChange={(e) => {
              // Past days can't be picked (a typed one snaps to today); on today, the time
              // can't be earlier than now
              const today = todayInput()
              const picked = e.target.value && e.target.value < today ? today : e.target.value
              setDate(picked)
              if (picked === today && time < nowTimeInput()) setTime(nowTimeInput())
              setResult(null)
            }}
          />
          <input
            type="time"
            style={{ flex: 1, minWidth: 0 }}
            min={date === todayInput() ? nowTimeInput() : undefined}
            value={time}
            onChange={(e) => {
              const earliest = date === todayInput() ? nowTimeInput() : '00:00'
              setTime(e.target.value && e.target.value < earliest ? earliest : e.target.value)
              setResult(null)
            }}
          />
        </div>
        <button
          className="primary full"
          disabled={!date || dayOver || !carePathId || !patientId || tooLong || noSteps || loading}
          onClick={() => find()}
        >
          {loading ? 'Searching…' : 'Find earliest'}
        </button>

        {tooLong && (
          <p className="error">
            This care path takes {carePath.total_minutes} min, longer than a clinic day ({dayMinutes} min).
          </p>
        )}
        {dayOver && <p className="error">Those days are in the past. Pick today or a later date.</p>}
        {noSteps && <p className="error">This care path has no steps.</p>}
        {error && <p className="error">{error}</p>}
      </div>

      <div className="panel">
        {!result && <p className="muted">Choose a care path and a patient, then search.</p>}
        {result && !result.found && (
          <p>
            {searchedNext ? 'No later slot is available' : 'No slot is available'} in the next{' '}
            {config.schedule_horizon_days === 1 ? 'day' : `${config.schedule_horizon_days} days`}.
          </p>
        )}
        {result?.found && result.start_time && result.end_time && (
          <>
            <div className="row" style={{ marginBottom: 12 }}>
              <h2 style={{ margin: 0, flex: 1 }}>
                {searchedNext ? 'Next' : 'Earliest'}: {formatDay(result.start_time)}, {formatTime(result.start_time)} –{' '}
                {formatTime(result.end_time)}
              </h2>
              {booked ? (
                <span>Scheduled ✓</span>
              ) : (
                <>
                  <button disabled={loading} onClick={() => find(true)}>
                    Next slot
                  </button>
                  <button className="primary" disabled={loading} onClick={book}>
                    Schedule
                  </button>
                </>
              )}
            </div>
            <Timeline
              fit
              date={toDateInput(new Date(result.start_time))}
              items={result.steps.map((s) => ({
                id: s.step_id,
                start: s.start_time,
                end: s.end_time,
                className: 'step',
                label: (
                  <>
                    <span>{s.name}</span>
                    <span className="muted">
                      {s.resource_id !== null && `${resourceName(s.resource_id)}, `}
                      {formatTime(s.start_time)}–{formatTime(s.end_time)}
                    </span>
                  </>
                ),
              }))}
            />
          </>
        )}
      </div>
    </div>
  )
}
