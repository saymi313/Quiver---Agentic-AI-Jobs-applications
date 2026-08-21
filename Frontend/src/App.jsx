import { useEffect, useState } from 'react'
import { AnimatePresence, motion as m } from 'motion/react'
import JobsTab from './tabs/JobsTab'
import ResumeTab from './tabs/ResumeTab'
import OutreachTab from './tabs/OutreachTab'
import TrackTab from './tabs/TrackTab'
import { api } from './lib/api'
import { springFor } from './lib/motion'
import { Note, Status } from './components/ui'

/*
  Four screens, named for the job they do rather than for the machinery behind
  them. The old labels ("Agent AI", "Auto Mode") described the implementation,
  which left the user guessing what each page was for.

  They are in the order the work happens: find a role, aim a resume at it,
  watch what comes back, and reach out directly where there is someone to
  reach.
*/
const TABS = [
  { key: 'jobs', label: 'Jobs' },
  { key: 'resume', label: 'Resume' },
  { key: 'track', label: 'Track' },
  { key: 'outreach', label: 'Outreach' },
]

/*
  The header's AI badge. It reports remaining daily calls once they run low,
  because the free tier is small enough to run out mid-session — and when it
  does, cover letters and form answers are quietly skipped. Silence there is
  worse than a warning.
*/
function AiStatus({ ai }) {
  const budget = ai.budget || {}
  const { cap = 0, remaining = 0, restingModels = [] } = budget

  if (!ai.available) {
    return <Status tone="warn" title={ai.reason}>AI not configured</Status>
  }
  if (cap && remaining <= 0) {
    return (
      <Status tone="bad" title={`Every model has spent its daily free-tier allowance. Resets tomorrow.`}>
        AI quota spent
      </Status>
    )
  }
  if (cap && remaining <= cap * 0.25) {
    return (
      <Status
        tone="warn"
        title={`${remaining} of ${cap} daily calls left${
          restingModels.length ? `. Resting: ${restingModels.join(', ')}` : ''
        }`}
      >
        {remaining} AI calls left
      </Status>
    )
  }
  return (
    <Status tone="ok" title={cap ? `${remaining} of ${cap} daily calls left` : ai.reason}>
      {ai.model}
    </Status>
  )
}

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

          {/* The underline is one shared element that springs between tabs
              rather than a border toggling on each button. It carries the eye
              from where you were to where you are, and because it is a spring
              it can be redirected mid-travel by a second click. */}
          <nav className="flex items-center gap-1" aria-label="Main">
            {TABS.map((t) => {
              const active = tab === t.key
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  aria-current={active ? 'page' : undefined}
                  className={`relative -mb-px h-13 px-3 text-sm transition-colors ${
                    active ? 'font-medium text-n-100' : 'text-n-400 hover:text-n-200'
                  }`}
                >
                  {t.label}
                  {active ? (
                    <m.span
                      layoutId="tab-underline"
                      transition={springFor()}
                      className="absolute inset-x-0 bottom-0 h-0.5 bg-accent"
                    />
                  ) : null}
                </button>
              )
            })}
          </nav>

          <div className="ml-auto">
            {offline ? (
              <Status tone="bad">API offline</Status>
            ) : health ? (
              <AiStatus ai={health.ai} />
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
        ) : (
          // A short settle rather than a slide: the screens are siblings, not
          // a stack, so there is no direction for one to come from. `mode
          // ="wait"` would add a hole where neither screen is on show.
          <AnimatePresence initial={false} mode="popLayout">
            <m.div
              key={tab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={springFor()}
            >
              {tab === 'jobs' ? (
                <JobsTab />
              ) : tab === 'resume' ? (
                <ResumeTab aiStatus={health?.ai} />
              ) : tab === 'track' ? (
                <TrackTab />
              ) : (
                <OutreachTab />
              )}
            </m.div>
          </AnimatePresence>
        )}
      </main>
    </div>
  )
}
