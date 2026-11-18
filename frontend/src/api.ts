import type { Block, Config, CarePath, Patient, Resource, ScheduleResponse } from './types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await fetch(BASE_URL + path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') {
        message = data.detail
      } else if (Array.isArray(data.detail)) {
        message = data.detail.map((d: { msg: string }) => d.msg).join('; ')
      }
    } catch {
      // response had no JSON body; keep the status text
    }
    throw new Error(message)
  }

  if (res.status === 204) {
    return undefined as T
  }
  return res.json() as Promise<T>
}

// Patients
export const listPatients = () => request<Patient[]>('/patients')
export const createPatient = (name: string) => request<Patient>('/patients', 'POST', { name })

// Resources
export const listResources = () => request<Resource[]>('/resources')
export const createResource = (name: string, type: string) =>
  request<Resource>('/resources', 'POST', { name, type })

// Care paths
export interface StepInput {
  name: string
  duration_minutes: number
  resource_id: number | null
  resource_type: string | null
}

export const listCarePaths = () => request<CarePath[]>('/care-paths')
export const createCarePath = (name: string) => request<CarePath>('/care-paths', 'POST', { name })
export const renameCarePath = (id: number, name: string) =>
  request<CarePath>(`/care-paths/${id}`, 'PUT', { name })
export const deleteCarePath = (id: number) => request<void>(`/care-paths/${id}`, 'DELETE')

export const addStep = (carePathId: number, step: StepInput) =>
  request<CarePath>(`/care-paths/${carePathId}/steps`, 'POST', step)
export const updateStep = (carePathId: number, stepId: number, step: StepInput) =>
  request<CarePath>(`/care-paths/${carePathId}/steps/${stepId}`, 'PUT', step)
export const deleteStep = (carePathId: number, stepId: number) =>
  request<CarePath>(`/care-paths/${carePathId}/steps/${stepId}`, 'DELETE')
export const reorderSteps = (carePathId: number, stepIds: number[]) =>
  request<CarePath>(`/care-paths/${carePathId}/steps`, 'PUT', { step_ids: stepIds })

// Blocks
export interface BlockFilter {
  patient_id?: number
  resource_id?: number
  start?: string
  end?: string
}

export interface BlockInput {
  patient_id: number | null
  resource_id: number | null
  start_time: string
  end_time: string
  reason: string | null
}

export const listBlocks = (filter: BlockFilter) => {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filter)) {
    if (value !== undefined) params.set(key, String(value))
  }
  return request<Block[]>(`/blocks?${params}`)
}
export const createBlock = (block: BlockInput) => request<Block>('/blocks', 'POST', block)
export const deleteBlock = (id: number) => request<void>(`/blocks/${id}`, 'DELETE')

// Schedule
export const findSchedule = (carePathId: number, patientId: number, start?: string, end?: string) =>
  request<ScheduleResponse>('/schedule', 'POST', {
    care_path_id: carePathId,
    patient_id: patientId,
    start,
    end,
  })

// Book a slot returned by findSchedule (blocks the patient and each step's resource)
export const bookSchedule = (carePathId: number, patientId: number, start: string) =>
  request<ScheduleResponse>('/schedule/book', 'POST', {
    care_path_id: carePathId,
    patient_id: patientId,
    start,
  })

// Scheduling settings (clinic hours, search horizon)
export const getConfig = () => request<Config>('/config')
