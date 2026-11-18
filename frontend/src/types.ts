export interface Patient {
  id: number
  name: string
}

export interface Resource {
  id: number
  name: string
  type: string
}

export interface CarePathStep {
  id: number
  position: number
  name: string
  duration_minutes: number
  resource_id: number | null
  resource_type: string | null
}

export interface CarePath {
  id: number
  name: string
  steps: CarePathStep[]
  total_minutes: number
}

export interface Block {
  id: number
  patient_id: number | null
  resource_id: number | null
  start_time: string
  end_time: string
  reason: string | null
}

export interface ScheduledStep {
  step_id: number
  name: string
  resource_id: number | null
  start_time: string
  end_time: string
}

export interface ScheduleResponse {
  found: boolean
  start_time: string | null
  end_time: string | null
  steps: ScheduledStep[]
}

export interface Config {
  slot_minutes: number
  schedule_horizon_days: number
  clinic_timezone: string
  clinic_open_hour: number
  clinic_close_hour: number
}
