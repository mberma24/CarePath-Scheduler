import { useCallback, useEffect, useState } from 'react'
import * as api from './api'
import FindTab from './FindTab'
import KPassesTab from './KPassesTab'
import RolePicker from './RolePicker'
import SchedulesTab from './SchedulesTab'
import type { Patient, Resource } from './types'

type Tab = 'kpasses' | 'schedules' | 'find'

const TABS: { id: Tab; label: string }[] = [
  { id: 'kpasses', label: 'K-passes' },
  { id: 'schedules', label: 'Schedules' },
  { id: 'find', label: 'Find earliest' },
]

// Demo role switcher, not real login: "admin", "patient:3", or "resource:5".
// The backend doesn't check roles; see "Future work" in the README.
const TABS_FOR: Record<string, Tab[]> = {
  admin: ['kpasses', 'schedules', 'find'], // everything
  patient: ['schedules', 'find'], // their own timeline, and finding a time for themselves
  resource: ['kpasses', 'schedules', 'find'], // their own timeline, K-passes, and finding times
}

export default function App() {
  const [tab, setTab] = useState<Tab>('kpasses')
  const [role, setRole] = useState('admin')
  const [patients, setPatients] = useState<Patient[]>([])
  const [resources, setResources] = useState<Resource[]>([])

  const loadPeople = useCallback(() => {
    Promise.all([api.listPatients(), api.listResources()])
      .then(([p, r]) => {
        setPatients(p)
        setResources(r)
      })
      .catch(() => {}) // the tabs show API errors themselves
  }, [])

  useEffect(loadPeople, [loadPeople])

  const allowed = TABS_FOR[role.split(':')[0]]

  function changeRole(value: string) {
    setRole(value)
    const tabs = TABS_FOR[value.split(':')[0]]
    if (!tabs.includes(tab)) setTab(tabs[0])
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-top">
          <h1>KPass Scheduler</h1>
          <RolePicker
            value={role}
            patients={patients}
            resources={resources}
            onChange={changeRole}
            onOpen={loadPeople}
          />
        </div>
        <nav className="tabs">
          {TABS.filter((t) => allowed.includes(t.id)).map(({ id, label }) => (
            <button key={id} className={id === tab ? 'tab active' : 'tab'} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
      </header>

      {/* key={role}: switching roles starts each tab fresh */}
      <main key={role}>
        {tab === 'kpasses' && <KPassesTab />}
        {tab === 'schedules' && <SchedulesTab lockedOwner={role === 'admin' ? undefined : role} />}
        {tab === 'find' && <FindTab lockedPatientId={role.startsWith('patient:') ? Number(role.split(':')[1]) : undefined} />}
      </main>
    </div>
  )
}
