import { useEffect, useRef, useState } from 'react'
import * as api from './api'
import type { StepInput } from './api'
import { SLOT_MINUTES } from './time'
import type { KPass, KPassStep, Resource } from './types'

// Round to the nearest slot (SLOT_MINUTES), between one slot and a clinic day, matching the backend
function snapMinutes(value: number, max: number): number {
  const snapped = Math.round(value / SLOT_MINUTES) * SLOT_MINUTES
  return Number.isFinite(snapped) ? Math.min(max, Math.max(SLOT_MINUTES, snapped)) : SLOT_MINUTES
}

// dayMinutes: length of a clinic day; no step (or K-pass) can be longer
export default function KPassesTab({ dayMinutes }: { dayMinutes: number }) {
  const [kpasses, setKPasses] = useState<KPass[]>([])
  const [resources, setResources] = useState<Resource[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [newName, setNewName] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([api.listKPasses(), api.listResources()])
      .then(([k, r]) => {
        setKPasses(k)
        setResources(r)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  // Run an API call, show its error if it fails
  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setError('')
    try {
      return await fn()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  function replace(updated: KPass) {
    setKPasses((list) => list.map((k) => (k.id === updated.id ? updated : k)))
  }

  async function create() {
    const created = await run(() => api.createKPass(newName))
    if (created) {
      setKPasses((list) => [...list, created])
      setSelectedId(created.id)
      setNewName('')
    }
  }

  async function remove(id: number) {
    await run(async () => {
      await api.deleteKPass(id)
      setKPasses((list) => list.filter((k) => k.id !== id))
      setSelectedId(null)
    })
  }

  const selected = kpasses.find((k) => k.id === selectedId)

  return (
    <div>
      {error && <p className="error">{error}</p>}

      <div className="split">
        <div className="panel stack">
          <h2>K-passes</h2>
          <div className="list tall">
            {kpasses.map((k) => (
              <button
                key={k.id}
                className={k.id === selectedId ? 'list-item active' : 'list-item'}
                onClick={() => setSelectedId(k.id === selectedId ? null : k.id)} // click again to unselect
              >
                <span>{k.name}</span>
                <span className="muted">{k.total_minutes} min</span>
              </button>
            ))}
            {kpasses.length === 0 && <p className="muted" style={{ padding: 8 }}>No K-passes yet.</p>}
          </div>
          <div className="row">
            <input
              placeholder="New K-pass name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              style={{ flex: 1 }}
            />
            <button className="primary" disabled={!newName.trim()} onClick={create}>
              Create
            </button>
          </div>
        </div>

        {selected ? (
          <KPassEditor
            key={selected.id}
            kpass={selected}
            resources={resources}
            dayMinutes={dayMinutes}
            run={run}
            onChange={replace}
            onDelete={() => remove(selected.id)}
          />
        ) : (
          <div className="panel">
            <p className="muted">Select a K-pass to edit its steps, or create a new one.</p>
          </div>
        )}
      </div>
    </div>
  )
}

interface EditorProps {
  kpass: KPass
  resources: Resource[]
  dayMinutes: number
  run: <T>(fn: () => Promise<T>) => Promise<T | undefined>
  onChange: (kpass: KPass) => void
  onDelete: () => void
}

function KPassEditor({ kpass, resources, dayMinutes, run, onChange, onDelete }: EditorProps) {
  const [name, setName] = useState(kpass.name)

  // Saves run one after another, so a step's auto-save and a quick ↑/↓ can't answer out of order
  const queue = useRef<Promise<void>>(Promise.resolve())
  function save(fn: () => Promise<KPass>) {
    queue.current = queue.current.then(async () => {
      const updated = await run(fn)
      if (updated) onChange(updated)
    })
  }

  function move(index: number, delta: number) {
    const ids = kpass.steps.map((s) => s.id)
    const [id] = ids.splice(index, 1)
    ids.splice(index + delta, 0, id)
    save(() => api.reorderSteps(kpass.id, ids))
  }

  return (
    <div className="panel">
      <div className="row" style={{ marginBottom: 12 }}>
        <input value={name} onChange={(e) => setName(e.target.value)} style={{ flex: 1, fontWeight: 600 }} />
        <span className="muted" style={{ marginRight: 8 }}>
          Total: {kpass.total_minutes} min
        </span>
        <button className="dark" disabled={!name.trim() || name === kpass.name} onClick={() => save(() => api.renameKPass(kpass.id, name))}>
          Rename
        </button>
        <button className="danger-solid" onClick={onDelete}>
          Delete K-pass
        </button>
      </div>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Step</th>
              <th>Minutes</th>
              <th>Resource</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {kpass.steps.map((step, i) => (
              <StepRow
                key={step.id}
                index={i}
                step={step}
                resources={resources}
                dayMinutes={dayMinutes}
                isFirst={i === 0}
                isLast={i === kpass.steps.length - 1}
                onMove={(delta) => move(i, delta)}
                onSave={(input) => save(() => api.updateStep(kpass.id, step.id, input))}
                onDelete={() => save(() => api.deleteStep(kpass.id, step.id))}
              />
            ))}
            <StepRow
              key={`new-${kpass.steps.length}`}
              resources={resources}
              dayMinutes={dayMinutes}
              onSave={(input) => save(() => api.addStep(kpass.id, input))}
            />
          </tbody>
        </table>
      </div>
    </div>
  )
}

interface StepRowProps {
  step?: KPassStep
  index?: number
  resources: Resource[]
  dayMinutes: number
  isFirst?: boolean
  isLast?: boolean
  onMove?: (delta: number) => void
  onSave: (input: StepInput) => void
  onDelete?: () => void
}

// One editable step; with no `step` it is the "add step" row
function StepRow({ step, index, resources, dayMinutes, isFirst, isLast, onMove, onSave, onDelete }: StepRowProps) {
  const [name, setName] = useState(step?.name ?? '')
  // Text, so the box can be blank while typing; snapped to a number when the box is left
  const [minutes, setMinutes] = useState(String(step?.duration_minutes ?? 30))
  // One <select> value for both kinds: "" (rest), "id:3" (a resource) or "type:doctor" (any of a type)
  const [resource, setResource] = useState(
    step?.resource_id != null ? `id:${step.resource_id}` : step?.resource_type ? `type:${step.resource_type}` : '',
  )
  const types = [...new Set(resources.map((r) => r.type))]

  function buildInput(selected = resource): StepInput {
    const [kind, value] = selected.split(/:(.*)/)
    return {
      name: name.trim(),
      duration_minutes: snapMinutes(Number(minutes), dayMinutes),
      resource_id: kind === 'id' ? Number(value) : null,
      resource_type: kind === 'type' ? value : null,
    }
  }

  // Existing steps save themselves when a field is left (or Enter / a new resource is picked)
  function autoSave(input = buildInput()) {
    if (!step) return
    if (!input.name) {
      setName(step.name) // an empty name isn't allowed; put the old one back
      return
    }
    const changed =
      input.name !== step.name ||
      input.duration_minutes !== step.duration_minutes ||
      input.resource_id !== step.resource_id ||
      input.resource_type !== step.resource_type
    if (changed) onSave(input)
  }

  const saveOnEnter = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') e.currentTarget.blur()
  }

  return (
    <tr>
      <td>{index === undefined ? '+' : index + 1}</td>
      <td>
        <input
          placeholder="Step name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => autoSave()}
          onKeyDown={saveOnEnter}
        />
      </td>
      <td>
        <input
          type="number"
          min={SLOT_MINUTES}
          step={SLOT_MINUTES}
          value={minutes}
          onChange={(e) => setMinutes(e.target.value)}
          onBlur={() => {
            setMinutes(String(snapMinutes(Number(minutes), dayMinutes)))
            autoSave()
          }}
          onKeyDown={saveOnEnter}
          style={{ width: 80 }}
        />
      </td>
      <td>
        <select
          value={resource}
          onChange={(e) => {
            setResource(e.target.value)
            autoSave(buildInput(e.target.value))
          }}
        >
          <option value="">Rest</option>
          <optgroup label="Any of type">
            {types.map((t) => (
              <option key={t} value={`type:${t}`}>
                Any {t}
              </option>
            ))}
          </optgroup>
          <optgroup label="Specific resource">
            {resources.map((r) => (
              <option key={r.id} value={`id:${r.id}`}>
                {r.name} ({r.type})
              </option>
            ))}
          </optgroup>
        </select>
      </td>
      <td>
        <div className="row">
        {step ? (
          <>
            <button disabled={isFirst} onClick={() => onMove?.(-1)}>
              ↑
            </button>
            <button disabled={isLast} onClick={() => onMove?.(1)}>
              ↓
            </button>
            <button className="danger" onClick={onDelete}>
              Delete
            </button>
          </>
        ) : (
          <button className="primary" disabled={!name.trim()} onClick={() => onSave(buildInput())}>
            Add step
          </button>
        )}
        </div>
      </td>
    </tr>
  )
}
