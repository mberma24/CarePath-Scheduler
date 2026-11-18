import { useEffect, useState } from 'react'
import * as api from './api'
import Timeline from './Timeline'
import { SLOT_MINUTES, dayRange, formatTime, isPast, searchMinutes, toDateInput, todayInput, toTimeInput } from './time'
import type { KPass, Patient, Resource, ScheduleResponse } from './types'

// lockedPatientId: a patient is viewing (demo roles), so they can only search for themselves
export default function FindTab({ lockedPatientId }: { lockedPatientId?: number }) {
  const [kpasses, setKPasses] = useState<KPass[]>([])
  const [patients, setPatients] = useState<Patient[]>([])
  const [resources, setResources] = useState<Resource[]>([])
  const [kpassId, setKPassId] = useState('')
  const [patientId, setPatientId] = useState(lockedPatientId ? String(lockedPatientId) : '')
  const [result, setResult] = useState<ScheduleResponse | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [date, setDate] = useState(() => toDateInput(new Date()))
  const [time, setTime] = useState(() => toTimeInput(new Date()))
  const [searchedNext, setSearchedNext] = useState(false)
  const [booked, setBooked] = useState(false)

  useEffect(() => {
    Promise.all([api.listKPasses(), api.listPatients(), api.listResources()])
      .then(([k, p, r]) => {
        setKPasses(k)
        setPatients(p)
        setResources(r)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  // Search from the chosen date/time (never before now) until midnight at the end of that day
  const chosenStart = new Date(`${date}T${time || '00:00'}`)
  const searchEnd = dayRange(date).end
  const minutesLeft = searchMinutes(chosenStart, new Date(searchEnd))
  const dayOver = isPast(searchEnd)
  const startPassed = !dayOver && isPast(chosenStart.toISOString())

  const kpass = kpasses.find((k) => String(k.id) === kpassId)
  const tooLong = kpass !== undefined && !dayOver && kpass.total_minutes > minutesLeft
  const noSteps = kpass !== undefined && kpass.steps.length === 0

  const resourceName = (id: number | null) =>
    id === null ? 'Patient only' : (resources.find((r) => r.id === id)?.name ?? `#${id}`)

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
      setResult(await api.findSchedule(Number(kpassId), Number(patientId), start.toISOString(), searchEnd))
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
      await api.bookSchedule(Number(kpassId), Number(patientId), result.start_time)
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
          value={kpassId}
          onChange={(e) => {
            setKPassId(e.target.value)
            setResult(null)
          }}
        >
          <option value="">Choose a K-pass…</option>
          {kpasses.map((k) => (
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
              setDate(e.target.value)
              setResult(null)
            }}
          />
          <input
            type="time"
            style={{ flex: 1, minWidth: 0 }}
            value={time}
            onChange={(e) => {
              setTime(e.target.value)
              setResult(null)
            }}
          />
        </div>
        <button
          className="primary full"
          disabled={!date || dayOver || !kpassId || !patientId || tooLong || noSteps || loading}
          onClick={() => find()}
        >
          {loading ? 'Searching…' : 'Find earliest'}
        </button>

        {tooLong && (
          <p className="error">
            {startPassed
              ? `${formatTime(chosenStart.toISOString())} has already passed. Pick a later time or date.`
              : `This K-pass takes ${kpass.total_minutes} min, but only ${minutesLeft} min are left that day.`}
          </p>
        )}
        {dayOver && <p className="error">That day is in the past. Pick today or a later date.</p>}
        {noSteps && <p className="error">This K-pass has no steps.</p>}
        {error && <p className="error">{error}</p>}
      </div>

      <div className="panel">
        {!result && <p className="muted">Choose a K-pass and a patient, then search.</p>}
        {result && !result.found && (
          <p>{searchedNext ? 'No later slot is available that day.' : 'No slot is available for the rest of that day.'}</p>
        )}
        {result?.found && result.start_time && result.end_time && (
          <>
            <div className="row" style={{ marginBottom: 12 }}>
              <h2 style={{ margin: 0, flex: 1 }}>
                {searchedNext ? 'Next' : 'Earliest'}: {formatTime(result.start_time)} – {formatTime(result.end_time)}
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
                      {resourceName(s.resource_id)} · {formatTime(s.start_time)}–{formatTime(s.end_time)}
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
