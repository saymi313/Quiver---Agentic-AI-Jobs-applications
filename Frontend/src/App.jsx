import { useEffect, useState } from 'react'
import JobsTab from './tabs/JobsTab'
import ResumeTab from './tabs/ResumeTab'
import OutreachTab from './tabs/OutreachTab'
import { api } from './lib/api'
import { Note, Status } from './components/ui'

/*
  Three screens, named for the job they do rather than for the machinery
  behind them. The old labels ("Agent AI", "Auto Mode") described the
  implementation, which left the user guessing what each page was for.
*/
const TABS = [
  { key: 'jobs', label: 'Jobs' },
  { key: 'resume', label: 'Resume' },
  { key: 'outreach', label: 'Outreach' },
]

export default function App() {
  const [tab, setTab] = useState('jobs')
  const [health, setHealth] = useState(null)
  const [offline, setOffline] = useState(false)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setOffline(true))
  }, [])

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-30 border-b border-line bg-canvas">
        <div className="mx-auto flex h-13 max-w-6xl items-center gap-6 px-6">
          <span className="text-sm font-semibold tracking-tight text-n-100">Quiver</span>

          <nav className="flex items-center gap-1" aria-label="Main">
            {TABS.map((t) => {
              const active = tab === t.key
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  aria-current={active ? 'page' : undefined}
                  className={`-mb-px h-13 border-b-2 px-3 text-sm transition-colors ${
                    active
                      ? 'border-accent font-medium text-n-100'
                      : 'border-transparent text-n-400 hover:text-n-200'
                  }`}
                >
                  {t.label}
                </button>
              )
            })}
          </nav>

          <div className="ml-auto">
            {offline ? (
              <Status tone="bad">API offline</Status>
            ) : health ? (
              <Status tone={health.ai.available ? 'ok' : 'warn'} title={health.ai.reason}>
                {health.ai.available ? health.ai.model : 'AI not configured'}
              </Status>
            ) : (
              <Status tone="neutral">connecting</Status>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-7">
        {offline ? (
          <Note tone="bad" title="The backend is not responding">
            From the <code className="text-n-200">Backend</code> folder run{' '}
            <code className="text-n-200">python run_dashboard.py</code>, then reload this page.
          </Note>
        ) : tab === 'jobs' ? (
          <JobsTab />
        ) : tab === 'resume' ? (
          <ResumeTab aiStatus={health?.ai} />
        ) : (
          <OutreachTab />
        )}
      </main>
    </div>
  )
}
