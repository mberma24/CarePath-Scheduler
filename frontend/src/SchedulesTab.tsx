import { useEffect, useRef, useState } from 'react'
import * as api from './api'
import Timeline from './Timeline'
import { SLOT_MINUTES, dayRange, formatTime, isoToMinute, minuteToIso, toDateInput } from './time'
import type { Block, Patient, Resource } from './types'

interface Owner {
  key: string // "patient:3" or "resource:5"
  name: string
  kind: string
  patient_id: number | null
  resource_id: number | null
}

interface Props {
  lockedOwner?: string // someone is signed in (demo roles), so only their own schedule is shown
  hours: [number, number] // clinic open and close hour; the timeline shows only these
}

export default function SchedulesTab({ lockedOwner, hours }: Props) {
  const [patients, setPatients] = useState<Patient[]>([])
  const [resources, setResources] = useState<Resource[]>([])
  const [error, setError] = useState('')

  const [patientName, setPatientName] = useState('')
  const [resourceName, setResourceName] = useState('')
  const [resourceType, setResourceType] = useState('')

  const [query, setQuery] = useState('')
  const [ownerKey, setOwnerKey] = useState(lockedOwner ?? '')
  const [date, setDate] = useState(toDateInput(new Date()))
  const [blocks, setBlocks] = useState<Block[]>([])

  // Press and drag over rows to select a range; `dragStart` is the row the press began on
  const dragStart = useRef<number | null>(null)
  const [selection, setSelection] = useState<{ start: number; end: number } | null>(null)
  const [reason, setReason] = useState('')

  useEffect(() => {
    Promise.all([api.listPatients(), api.listResources()])
      .then(([p, r]) => {
        setPatients(p)
        setResources(r)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  // Releasing the mouse anywhere ends a drag
  useEffect(() => {
    const endDrag = () => {
      dragStart.current = null
    }
    window.addEventListener('mouseup', endDrag)
    return () => window.removeEventListener('mouseup', endDrag)
  }, [])

  const owners: Owner[] = [
    ...patients.map((p) => ({ key: `patient:${p.id}`, name: p.name, kind: 'patient', patient_id: p.id, resource_id: null })),
    ...resources.map((r) => ({ key: `resource:${r.id}`, name: r.name, kind: r.type, patient_id: null, resource_id: r.id })),
  ]
  const owner = owners.find((o) => o.key === ownerKey)
  const q = query.trim().toLowerCase()
  const visible = owners.filter((o) => o.name.toLowerCase().includes(q) || o.kind.toLowerCase().includes(q))

  useEffect(() => {
    const [kind, id] = ownerKey.split(':')
    if (!id || !date) return
    const { start, end } = dayRange(date)
    api
      .listBlocks({ [`${kind}_id`]: Number(id), start, end })
      .then(setBlocks)
      .catch((e: Error) => setError(e.message))
  }, [ownerKey, date])

  async function run(fn: () => Promise<void>) {
    setError('')
    try {
      await fn()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  function clearSelection() {
    dragStart.current = null
    setSelection(null)
  }

  function selectOwner(key: string) {
    setOwnerKey(key === ownerKey ? '' : key) // clicking the selected one again unselects it
    setBlocks([])
    clearSelection()
  }

  // Existing blocks as minutes after midnight, so a selection can't run into them
  const busy = blocks.map((b) => ({ start: isoToMinute(date, b.start_time), end: isoToMinute(date, b.end_time) }))
  const isBusy = (start: number, end: number) => busy.some((b) => b.start < end && start < b.end)

  function pressSlot(minute: number) {
    if (isBusy(minute, minute + SLOT_MINUTES)) return
    dragStart.current = minute
    setSelection({ start: minute, end: minute + SLOT_MINUTES })
  }

  function dragOverSlot(minute: number) {
    const anchor = dragStart.current
    if (anchor === null) return
    let start = Math.min(anchor, minute)
    let end = Math.max(anchor, minute) + SLOT_MINUTES
    // Stop at the first block in the drag direction instead of selecting across it
    for (const b of busy) {
      if (b.start < end && start < b.end) {
        if (minute >= anchor) end = Math.min(end, Math.floor(b.start / SLOT_MINUTES) * SLOT_MINUTES)
        else start = Math.max(start, Math.ceil(b.end / SLOT_MINUTES) * SLOT_MINUTES)
      }
    }
    setSelection(end > start ? { start, end } : { start: anchor, end: anchor + SLOT_MINUTES })
  }

  const addPatient = () =>
    run(async () => {
      const created = await api.createPatient(patientName)
      setPatients((list) => [...list, created])
      setPatientName('')
    })

  const addResource = () =>
    run(async () => {
      const created = await api.createResource(resourceName, resourceType)
      setResources((list) => [...list, created])
      setResourceName('')
      setResourceType('')
    })

  const addBlock = () =>
    run(async () => {
      if (!owner || !selection) return
      const created = await api.createBlock({
        patient_id: owner.patient_id,
        resource_id: owner.resource_id,
        start_time: minuteToIso(date, selection.start),
        end_time: minuteToIso(date, selection.end),
        reason: reason.trim() || null,
      })
      setBlocks((list) => [...list, created])
      setReason('')
      clearSelection()
    })

  const removeBlock = (id: number) =>
    run(async () => {
      await api.deleteBlock(id)
      setBlocks((list) => list.filter((b) => b.id !== id))
    })

  return (
    <div>
      {error && <p className="error">{error}</p>}

      <div className={lockedOwner ? undefined : 'split'}>
        {!lockedOwner && (
        <div>
          <div className="panel stack">
            <h2>Patients & resources</h2>
            <input className="full" placeholder="Search patients and resources" value={query} onChange={(e) => setQuery(e.target.value)} />
            <div className="list">
              {visible.map((o) => (
                <button key={o.key} className={o.key === ownerKey ? 'list-item active' : 'list-item'} onClick={() => selectOwner(o.key)}>
                  <span>{o.name}</span>
                  <span className="muted">{o.kind}</span>
                </button>
              ))}
              {visible.length === 0 && <p className="muted" style={{ padding: 8 }}>No matches.</p>}
            </div>
          </div>
          <div className="panel stack">
            <h2>Add patient or resource</h2>
            <div className="label">Patient</div>
            <div className="row">
              <input placeholder="Patient name" value={patientName} onChange={(e) => setPatientName(e.target.value)} style={{ flex: 1, minWidth: 0 }} />
              <button className="primary" disabled={!patientName.trim()} onClick={addPatient}>
                Add patient
              </button>
            </div>
            <hr className="divider" />
            <div className="label">Resource</div>
            <input className="full" placeholder="Name, e.g. Dr. Lee" value={resourceName} onChange={(e) => setResourceName(e.target.value)} />
            <input className="full" placeholder="Role, e.g. Doctor" value={resourceType} onChange={(e) => setResourceType(e.target.value)} />
            <button className="full primary" disabled={!resourceName.trim() || !resourceType.trim()} onClick={addResource}>
              Add resource
            </button>
          </div>
        </div>
        )}

        <div className="panel">
          {!owner ? (
            <p className="muted">{lockedOwner ? 'Loading…' : 'Select a patient or resource to see their schedule.'}</p>
          ) : (
            <>
              {/* Selection controls share the header row so the timeline never moves mid-drag */}
              <div className="row" style={{ marginBottom: 12, minHeight: 36 }}>
                <h2 style={{ margin: 0, flex: 1 }}>{owner.name}</h2>
                {selection && (
                  <>
                    <span>
                      {formatTime(minuteToIso(date, selection.start))} – {formatTime(minuteToIso(date, selection.end))}
                    </span>
                    <input placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
                    <button className="primary" onClick={addBlock}>
                      Block
                    </button>
                    <button onClick={clearSelection}>Cancel</button>
                  </>
                )}
                <input
                  type="date"
                  value={date}
                  onChange={(e) => {
                    setDate(e.target.value)
                    clearSelection()
                  }}
                />
              </div>

              <Timeline
                date={date}
                hours={hours}
                selection={selection}
                onSlotPress={pressSlot}
                onSlotEnter={dragOverSlot}
                items={blocks.map((b) => ({
                  id: b.id,
                  start: b.start_time,
                  end: b.end_time,
                  className: 'blocked',
                  label: (
                    <>
                      <span>{b.reason || 'Blocked'}</span>
                      <button className="danger" onClick={() => removeBlock(b.id)}>
                        ×
                      </button>
                    </>
                  ),
                }))}
              />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
