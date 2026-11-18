import { useState } from 'react'

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
        {tab === 'kpasses' && <p>K-pass builder goes here.</p>}
        {tab === 'schedules' && <p>Schedules and blocks go here.</p>}
        {tab === 'find' && <p>Find earliest goes here.</p>}
      </main>
    </div>
  )
}