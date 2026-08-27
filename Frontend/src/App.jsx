import { useEffect, useState } from 'react'
import { AnimatePresence, motion as m } from 'motion/react'
import DashboardTab from './tabs/DashboardTab'
import JobsTab from './tabs/JobsTab'
import ResumeTab from './tabs/ResumeTab'
import OutreachTab from './tabs/OutreachTab'
import TrackTab from './tabs/TrackTab'
import ProfilesTab from './tabs/ProfilesTab'
import ResearchTab from './tabs/ResearchTab'
import SettingsTab from './tabs/SettingsTab'
import ResumeProfilePage from './components/ResumeProfilePage'
import { api } from './lib/api'
import { springFor } from './lib/motion'
import { usePress } from './lib/usePress'
import { Icon, Note, Status } from './components/ui'

/*
  The app shell: a sidebar and a page.

  Four screens, named for the job they do rather than for the machinery behind
  them, in the order the work happens — find a role, aim a resume at it, watch
  what comes back, and reach out directly where there is someone to reach.

  A sidebar rather than a top tab bar because the destinations are a permanent
  list rather than a mode switch, and because it has room for the counts that
  say which of them needs you. The rail is a translucent material with the page
  passing under it; content surfaces stay opaque, because stacking one
  translucent layer on another is where legibility goes.
*/

/*
  Two groups, because the destinations answer two different questions.

  The first is the work: what is happening, what to act on, what came back, who
  to reach. The second is the setup behind it — which resume, and how the agent
  behaves. Splitting them is what let the search settings, the portal table and
  the whole configuration panel come off the Jobs screen, where they had been
  sitting above the table people actually open the app to use.
*/
const GROUPS = [
  {
    label: 'Workspace',
    tabs: [
      { key: 'dashboard', label: 'Dashboard', icon: Icon.Home },
      { key: 'jobs', label: 'Jobs', icon: Icon.Briefcase },
      { key: 'track', label: 'Track', icon: Icon.Inbox },
      { key: 'outreach', label: 'Outreach', icon: Icon.Send },
      { key: 'research', label: 'Research', icon: Icon.Search },
    ],
  },
  {
    label: 'Setup',
    tabs: [
      { key: 'profiles', label: 'Profiles', icon: Icon.User },
      { key: 'resume', label: 'Resume check', icon: Icon.File },
      { key: 'settings', label: 'Settings', icon: Icon.Gear },
    ],
  },
]

const TABS = GROUPS.flatMap((g) => g.tabs)

/*
  The AI badge. It reports remaining daily calls once they run low, because the
  free tier is small enough to run out mid-session — and when it does, cover
  letters and form answers are quietly skipped. Silence there is worse than a
  warning.
*/
function AiStatus({ ai }) {
  const budget = ai.budget || {}
  const { cap = 0, remaining = 0, restingModels = [] } = budget

  if (!ai.available) {
    return <Status tone="warn" title={ai.reason}>AI not configured</Status>
  }
  if (cap && remaining <= 0) {
    return (
      <Status tone="bad" title="Every model has spent its daily free-tier allowance. Resets tomorrow.">
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

/** One destination in the rail. The selected pill is a single shared element
 *  that springs between items, so the eye is carried rather than teleported. */
function NavItem({ tab, active, badge, onSelect }) {
  const { pressed, handlers } = usePress({ onPress: onSelect })
  const IconFor = tab.icon
  return (
    <button
      {...handlers}
      onClick={(event) => event.detail === 0 && onSelect()}
      data-pressed={pressed}
      aria-current={active ? 'page' : undefined}
      className={`press relative flex w-full items-center gap-2.5 rounded-sm px-2.5 py-1.5
        text-sm ${active ? 'font-medium text-n-100' : 'text-n-400 hover:text-n-100'}`}
    >
      {active ? (
        <m.span
          layoutId="nav-selected"
          transition={springFor()}
          className="absolute inset-0 -z-10 rounded-sm bg-n-850"
        />
      ) : null}
      <IconFor className={active ? 'size-4 text-n-100' : 'size-4 text-n-500'} />
      <span className="flex-1 text-left">{tab.label}</span>
      {badge ? (
        <span className="rounded-full bg-n-800 px-1.5 py-px text-micro font-medium text-n-400">
          {badge > 99 ? '99+' : badge}
        </span>
      ) : null}
    </button>
  )
}

function getRouteFromHash() {
  const hash = window.location.hash.replace(/^#\/?/, '').trim()
  if (!hash) return { tab: 'dashboard', slug: null }
  const parts = hash.split('/')
  if (parts[0] === 'profiles' && parts[1]) {
    return { tab: 'profile-detail', slug: decodeURIComponent(parts[1]) }
  }
  if (parts[0] === 'resumes' && parts[1]) {
    return { tab: 'profile-detail', slug: decodeURIComponent(parts[1]) }
  }
  const known = ['dashboard', 'jobs', 'track', 'outreach', 'research', 'profiles', 'resume', 'settings']
  if (known.includes(parts[0])) {
    return { tab: parts[0], slug: null }
  }
  return { tab: 'dashboard', slug: null }
}

export default function App() {
  const [route, setRoute] = useState(getRouteFromHash)
  const [health, setHealth] = useState(null)
  const [offline, setOffline] = useState(false)
  const [counts, setCounts] = useState({})

  const activeTab = route.tab === 'profile-detail' ? 'profiles' : route.tab

  useEffect(() => {
    const handleHashChange = () => {
      setRoute(getRouteFromHash())
    }
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  const navigateTab = (tabKey) => {
    window.location.hash = `#/${tabKey}`
  }

  useEffect(() => {
    api.health().then(setHealth).catch(() => setOffline(true))
  }, [])

  // The rail's counts: what is waiting on you, per destination. Polled rather
  // than pushed, because nothing here changes faster than a person reads.
  useEffect(() => {
    let alive = true
    const read = () =>
      Promise.all([
        api.agentTracker().catch(() => null),
        api.agentProposals().catch(() => null),
      ]).then(([tracker, proposals]) => {
        if (!alive) return
        setCounts({
          track: tracker?.unread || 0,
          jobs: proposals?.rows?.length || 0,
        })
      })
    read()
    const timer = setInterval(read, 60000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [route])

  return (
    <div className="flex min-h-full">
      {/* ------------------------------------------------------------ rail */}
      <aside className="material sticky top-0 hidden h-screen w-56 shrink-0 flex-col
        border-r border-line px-3 py-4 md:flex">
        <div className="flex items-center px-2.5 pb-5">
          <img src="/logo.png" alt="Jobenzy logo" className="h-8 w-auto object-contain" />
        </div>
        <nav className="flex-1 space-y-4">
          {GROUPS.map((group) => (
            <div key={group.label}>
              <p className="px-2.5 pb-1.5 text-micro font-medium tracking-wide text-n-500 uppercase">
                {group.label}
              </p>
              <div className="flex flex-col gap-0.5">
                {group.tabs.map((t) => (
                  <NavItem
                    key={t.key}
                    tab={t}
                    active={activeTab === t.key}
                    badge={counts[t.key]}
                    onSelect={() => navigateTab(t.key)}
                  />
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="mt-auto space-y-3 pt-6">
          <div className="rounded-md border border-line bg-surface px-3 py-2.5">
            <p className="text-micro font-medium tracking-wide text-n-500 uppercase">Model</p>
            <div className="mt-1.5">
              {offline ? (
                <Status tone="bad">API offline</Status>
              ) : health ? (
                <AiStatus ai={health.ai} />
              ) : (
                <Status tone="neutral">connecting</Status>
              )}
            </div>
          </div>
        </div>
      </aside>

      {/* ------------------------------------------------------------ page */}
      <div className="min-w-0 flex-1">
        {/* On a narrow screen the rail collapses to a top bar: the same four
            destinations, still one tap away. */}
        <header className="material sticky top-0 z-30 flex items-center gap-1 border-b
          border-line px-4 py-2 md:hidden">
          <img src="/logo.png" alt="Jobenzy logo" className="size-5 shrink-0 object-contain" />
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => navigateTab(t.key)}
              aria-current={activeTab === t.key ? 'page' : undefined}
              className={`press rounded-full px-3 py-1 text-sm ${
                activeTab === t.key ? 'bg-n-850 font-medium text-n-100' : 'text-n-400'
              }`}
            >
              {t.label}
            </button>
          ))}
        </header>

        <main className="mx-auto max-w-6xl px-6 py-8 lg:px-10">
          {offline ? (
            <Note tone="bad" title="The backend is not responding">
              From the <code className="text-n-200">Backend</code> folder run{' '}
              <code className="text-n-200">python run_dashboard.py</code>, then reload this page.
            </Note>
          ) : (
            // A short settle rather than a slide: the screens are siblings, not
            // a stack, so there is no direction for one to come from.
            <AnimatePresence initial={false} mode="popLayout">
              <m.div
                key={route.tab === 'profile-detail' ? `profile-${route.slug}` : route.tab}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={springFor()}
              >
                {route.tab === 'profile-detail' ? (
                  <ResumeProfilePage
                    profileName={route.slug}
                    onBack={() => {
                      window.location.hash = '#/profiles'
                    }}
                  />
                ) : route.tab === 'dashboard' ? (
                  <DashboardTab onOpenJobs={() => navigateTab('jobs')} />
                ) : route.tab === 'jobs' ? (
                  <JobsTab />
                ) : route.tab === 'track' ? (
                  <TrackTab />
                ) : route.tab === 'outreach' ? (
                  <OutreachTab />
                ) : route.tab === 'research' ? (
                  <ResearchTab />
                ) : route.tab === 'profiles' ? (
                  <ProfilesTab />
                ) : route.tab === 'resume' ? (
                  <ResumeTab aiStatus={health?.ai} />
                ) : (
                  <SettingsTab />
                )}
              </m.div>
            </AnimatePresence>
          )}
        </main>
      </div>
    </div>
  )
}
