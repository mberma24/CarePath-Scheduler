import { useState } from 'react'
import FindTab from './FindTab'
import KPassesTab from './KPassesTab'
import SchedulesTab from './SchedulesTab'

type Tab = 'kpasses' | 'schedules' | 'find'

const TABS: { id: Tab; label: string }[] = [
  { id: 'kpasses', label: 'K-passes' },
  { id: 'schedules', label: 'Schedules' },
  { id: 'find', label: 'Find earliest' },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('kpasses')

  return (
    <div className="app">
      <header className="header">
        <h1>KPass Scheduler</h1>
        <nav className="tabs">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              className={id === tab ? 'tab active' : 'tab'}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main>
        {tab === 'kpasses' && <KPassesTab />}
        {tab === 'schedules' && <SchedulesTab />}
        {tab === 'find' && <FindTab />}
      </main>
    </div>
  )
}