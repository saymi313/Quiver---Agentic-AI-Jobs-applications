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

function AiStatus({ ai, compact = false }) {
  const budget = ai.budget || {}
  const { cap = 0, remaining = 0, restingModels = [] } = budget

  if (!ai.available) {
    return <Status tone="warn" title={ai.reason}>{compact ? 'Offline' : 'AI not configured'}</Status>
  }
  if (cap && remaining <= 0) {
    return (
      <Status tone="bad" title="Every model has spent its daily free-tier allowance. Resets tomorrow.">
        {compact ? 'Quota 0' : 'AI quota spent'}
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
        {compact ? `${remaining}` : `${remaining} AI calls left`}
      </Status>
    )
  }
  return (
    <Status tone="ok" title={cap ? `${remaining} of ${cap} daily calls left` : ai.reason}>
      {compact ? 'Active' : ai.model}
    </Status>
  )
}

function NavItem({ tab, active, badge, collapsed, onSelect }) {
  const { pressed, handlers } = usePress({ onPress: onSelect })
  const IconFor = tab.icon
  return (
    <button
      {...handlers}
      onClick={(event) => event.detail === 0 && onSelect()}
      data-pressed={pressed}
      aria-current={active ? 'page' : undefined}
      title={collapsed ? `${tab.label}${badge ? ` (${badge})` : ''}` : undefined}
      className={`press relative flex w-full items-center ${
        collapsed ? 'justify-center px-0 py-2.5' : 'gap-2.5 px-2.5 py-1.5'
      } rounded-sm text-sm ${active ? 'font-medium text-n-100' : 'text-n-400 hover:text-n-100'}`}
    >
      {active ? (
        <m.span
          layoutId="nav-selected"
          transition={springFor()}
          className="absolute inset-0 -z-10 rounded-sm bg-n-850"
        />
      ) : null}
      <div className="relative">
        <IconFor className={active ? 'size-4 text-n-100' : 'size-4 text-n-500'} />
        {collapsed && badge ? (
          <span className="absolute -top-1 -right-1 flex size-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex rounded-full size-2 bg-blue-500" />
          </span>
        ) : null}
      </div>
      {!collapsed ? (
        <>
          <span className="flex-1 text-left truncate">{tab.label}</span>
          {badge ? (
            <span className="rounded-full bg-n-800 px-1.5 py-px text-micro font-medium text-n-400">
              {badge > 99 ? '99+' : badge}
            </span>
          ) : null}
        </>
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem('jobenzy_sidebar_collapsed') === 'true'
  })
  const [mobileOpen, setMobileOpen] = useState(false)

  const activeTab = route.tab === 'profile-detail' ? 'profiles' : route.tab
  const currentTabObj = TABS.find((t) => t.key === activeTab) || TABS[0]

  useEffect(() => {
    const handleHashChange = () => {
      setRoute(getRouteFromHash())
      setMobileOpen(false)
    }
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  // Keyboard shortcut: Cmd+B / Ctrl+B to toggle sidebar on desktop
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault()
        toggleSidebar()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev
      localStorage.setItem('jobenzy_sidebar_collapsed', String(next))
      return next
    })
  }

  const navigateTab = (tabKey) => {
    window.location.hash = `#/${tabKey}`
    setMobileOpen(false)
  }

  useEffect(() => {
    api.health().then(setHealth).catch(() => setOffline(true))
  }, [])

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
      {/* ------------------------------------------------------------ Desktop Rail */}
      <m.aside
        animate={{ width: sidebarCollapsed ? 68 : 224 }}
        transition={springFor()}
        className="material sticky top-0 hidden h-screen shrink-0 flex-col border-r border-line px-2.5 py-4 md:flex overflow-hidden z-20"
      >
        <div className="flex items-center justify-between px-1.5 pb-5">
          {!sidebarCollapsed ? (
            <div className="flex items-center gap-2">
              <img src="/logo.png" alt="Jobenzy logo" className="h-7 w-auto object-contain" />
            </div>
          ) : (
            <div className="mx-auto">
              <img src="/logo.png" alt="Jobenzy logo" className="h-6 w-auto object-contain" />
            </div>
          )}
          <button
            onClick={toggleSidebar}
            title={sidebarCollapsed ? 'Expand sidebar (Ctrl+B)' : 'Collapse sidebar (Ctrl+B)'}
            className="press rounded-md p-1.5 text-n-400 hover:bg-n-800 hover:text-n-100 transition-colors"
            aria-label="Toggle sidebar"
          >
            {sidebarCollapsed ? (
              <Icon.Sidebar className="size-4" />
            ) : (
              <Icon.SidebarCollapse className="size-4" />
            )}
          </button>
        </div>

        <nav className="flex-1 space-y-4 overflow-y-auto">
          {GROUPS.map((group) => (
            <div key={group.label}>
              {!sidebarCollapsed ? (
                <p className="px-2.5 pb-1.5 text-micro font-medium tracking-wide text-n-500 uppercase">
                  {group.label}
                </p>
              ) : (
                <div className="my-1.5 border-t border-line/60 mx-1" />
              )}
              <div className="flex flex-col gap-0.5">
                {group.tabs.map((t) => (
                  <NavItem
                    key={t.key}
                    tab={t}
                    active={activeTab === t.key}
                    badge={counts[t.key]}
                    collapsed={sidebarCollapsed}
                    onSelect={() => navigateTab(t.key)}
                  />
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="mt-auto space-y-2 pt-4">
          <div className={`rounded-md border border-line bg-surface ${sidebarCollapsed ? 'p-2 text-center' : 'px-3 py-2.5'}`}>
            {!sidebarCollapsed ? (
              <>
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
              </>
            ) : (
              <div className="flex justify-center" title={health?.ai?.model || 'Model'}>
                {offline ? (
                  <span className="size-2.5 rounded-full bg-bad-500" />
                ) : health?.ai?.available ? (
                  <span className="size-2.5 rounded-full bg-ok-500" />
                ) : (
                  <span className="size-2.5 rounded-full bg-amber-500" />
                )}
              </div>
            )}
          </div>
        </div>
      </m.aside>

      {/* ------------------------------------------------------------ Mobile Navigation & Drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            {/* Backdrop */}
            <m.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileOpen(false)}
              className="fixed inset-0 z-40 bg-black/60 backdrop-blur-xs md:hidden"
            />

            {/* Mobile Drawer */}
            <m.aside
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={springFor()}
              className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col border-r border-line bg-surface p-4 shadow-2xl md:hidden"
            >
              <div className="flex items-center justify-between pb-4 border-b border-line">
                <div className="flex items-center gap-2">
                  <img src="/logo.png" alt="Jobenzy logo" className="h-7 w-auto object-contain" />
                  <span className="text-sm font-bold text-n-100">Jobenzy</span>
                </div>
                <button
                  onClick={() => setMobileOpen(false)}
                  className="press rounded-full p-1.5 text-n-400 hover:bg-n-800 hover:text-n-100"
                  aria-label="Close navigation"
                >
                  <Icon.X className="size-4" />
                </button>
              </div>

              <nav className="flex-1 space-y-4 overflow-y-auto pt-4">
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
                          collapsed={false}
                          onSelect={() => navigateTab(t.key)}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </nav>

              <div className="mt-auto pt-4 border-t border-line">
                <div className="rounded-md border border-line bg-n-900 px-3 py-2.5">
                  <p className="text-micro font-medium tracking-wide text-n-500 uppercase">Model</p>
                  <div className="mt-1">
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
            </m.aside>
          </>
        )}
      </AnimatePresence>

      {/* ------------------------------------------------------------ Main Content Area */}
      <div className="min-w-0 flex-1">
        {/* Mobile Header Bar */}
        <header className="material sticky top-0 z-30 flex items-center justify-between border-b border-line px-4 py-2.5 md:hidden">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileOpen(true)}
              className="press rounded-md border border-line bg-surface p-1.5 text-n-200 hover:text-n-100 active:scale-[0.97]"
              aria-label="Open navigation menu"
            >
              <Icon.Menu className="size-4" />
            </button>
            <div className="flex items-center gap-2">
              <img src="/logo.png" alt="Jobenzy logo" className="size-5 object-contain" />
              <span className="text-sm font-semibold text-n-100 capitalize">
                {route.tab === 'profile-detail' ? `Profile: ${route.slug}` : currentTabObj.label}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {health?.ai ? <AiStatus ai={health.ai} compact /> : null}
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
          {offline ? (
            <Note tone="bad" title="The backend is not responding">
              From the <code className="text-n-200">Backend</code> folder run{' '}
              <code className="text-n-200">python run_dashboard.py</code>, then reload this page.
            </Note>
          ) : (
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
