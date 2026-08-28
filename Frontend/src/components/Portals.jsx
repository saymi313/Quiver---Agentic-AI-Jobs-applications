import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Button, Disclosure, Empty, Icon, Input, Note, Status, Table, Td, Tr } from './ui'

/*
  Live Portals, Job Board Integrations & ATS Capabilities in Settings.
  Enables toggling active sources, connecting LinkedIn, running scans, and viewing ATS support.
*/

const SUBMIT_TONE = {
  proven: 'ok',
  likely: 'accent',
  unproven: 'neutral',
  no: 'warn',
}

const SUBMIT_LABEL = {
  proven: 'proven',
  likely: 'likely',
  unproven: 'untested',
  no: 'via employer',
}

export default function Portals({ open, onToggle, onFetched }) {
  const [data, setData] = useState(null)
  const [sources, setSources] = useState([])
  const [selectedSources, setSelectedSources] = useState(['linkedin', 'weworkremotely', 'jobicy', 'himalayas'])
  const [keywords, setKeywords] = useState('Software Engineer, Full Stack, React, Node.js')
  const [location, setLocation] = useState('Pakistan, Remote')
  const [limit, setLimit] = useState(20)
  const [fetching, setFetching] = useState(false)
  const [fetchResult, setFetchResult] = useState(null)
  const [fetchError, setFetchError] = useState('')

  // LinkedIn connection state
  const [profileUrl, setProfileUrl] = useState('')
  const [cookieLiAt, setCookieLiAt] = useState('')
  const [connected, setConnected] = useState(false)
  const [savingConnect, setSavingConnect] = useState(false)
  const [connectMsg, setConnectMsg] = useState('')

  useEffect(() => {
    if (!open) return
    if (!data) {
      api.agentPortals()
        .then(setData)
        .catch(() => setData({ rows: [], summary: {} }))
    }
    api.agentSourcesStatus()
      .then(res => {
        if (res?.sources) {
          setSources(res.sources)
          const linkedIn = res.sources.find(s => s.id === 'linkedin')
          if (linkedIn) {
            setConnected(linkedIn.connected || false)
            setProfileUrl(linkedIn.profile_url || '')
          }
        }
      })
      .catch(() => {})
  }, [open, data])

  const toggleSource = (id) => {
    setSelectedSources(prev =>
      prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]
    )
  }

  const handleFetch = async () => {
    setFetching(true)
    setFetchError('')
    setFetchResult(null)

    const kwList = keywords.split(',').map(s => s.trim()).filter(Boolean)
    const locList = location.split(',').map(s => s.trim()).filter(Boolean)

    try {
      const res = await api.agentSourcesFetch({
        sources: selectedSources,
        keywords: kwList.length ? kwList : ['Software Engineer'],
        locations: locList.length ? locList : ['Pakistan', 'Remote'],
        limit: Number(limit) || 20,
      })
      setFetchResult(res)
      onFetched?.()
    } catch (err) {
      setFetchError(err.message || 'Failed to fetch jobs from selected portals.')
    } finally {
      setFetching(false)
    }
  }

  const handleSaveLinkedIn = async () => {
    setSavingConnect(true)
    setConnectMsg('')
    try {
      const res = await api.agentConnectLinkedIn({
        profile_url: profileUrl,
        li_at: cookieLiAt,
      })
      if (res?.connected) {
        setConnected(true)
        setConnectMsg('LinkedIn session saved and authenticated successfully.')
      } else {
        setConnectMsg('LinkedIn settings saved.')
      }
    } catch (err) {
      setConnectMsg(err.message || 'Could not save connection.')
    } finally {
      setSavingConnect(false)
    }
  }

  const s = data?.summary || {}

  return (
    <Disclosure
      title="Live Portals & Job Sources"
      description="Active discovery boards (LinkedIn, WeWorkRemotely, Jobicy), LinkedIn session auth, and ATS submission support."
      open={open}
      onToggle={onToggle}
    >
      <div className="space-y-6">
        {/* Section 1: Active Job Sources */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-micro font-semibold uppercase tracking-wider text-n-300">
              Active Job Boards &amp; Discovery Sources
            </h4>
            <span className="text-micro text-n-400">
              {selectedSources.length} of {sources.length || 8} enabled
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {sources.map(src => {
              const active = selectedSources.includes(src.id)
              return (
                <button
                  key={src.id}
                  type="button"
                  onClick={() => toggleSource(src.id)}
                  className={`p-3 rounded-lg border text-left flex items-start justify-between transition-all ${
                    active
                      ? 'bg-accent-950/20 border-accent-500/40 text-n-100'
                      : 'bg-raised/40 border-line text-n-400 hover:border-line-strong'
                  }`}
                >
                  <div>
                    <div className="text-tiny font-semibold text-n-100 flex items-center gap-1.5">
                      <span>{src.name}</span>
                      {src.connected && (
                        <Status tone="ok" dot={true}>Connected</Status>
                      )}
                    </div>
                    <div className="text-micro text-n-400 mt-0.5">
                      Regions: {src.regions.join(', ')}
                    </div>
                  </div>
                  <div className={`size-4 rounded border flex items-center justify-center mt-0.5 ${
                    active ? 'bg-accent-500 border-accent-500 text-white' : 'border-line bg-surface'
                  }`}>
                    {active && <Icon.Check className="size-3 text-white" />}
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        {/* Section 2: LinkedIn Connection */}
        <div className="p-4 rounded-xl border border-line bg-surface-sunken/40 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Icon.Globe className="size-4 text-blue-400" />
              <h4 className="text-tiny font-semibold text-n-100">
                LinkedIn Session Authentication
              </h4>
            </div>
            {connected ? (
              <Status tone="ok" dot={true}>Session Active</Status>
            ) : (
              <Status tone="warn">Auth Required for Easy Apply</Status>
            )}
          </div>

          <p className="text-micro text-n-400 leading-relaxed">
            Attach your profile URL and <code className="text-accent-300">li_at</code> session cookie to bypass LinkedIn's guest auth walls and enable Easy Apply.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-micro font-medium text-n-300 block mb-1">
                LinkedIn Profile URL
              </label>
              <Input
                value={profileUrl}
                onChange={e => setProfileUrl(e.target.value)}
                placeholder="https://www.linkedin.com/in/your-profile/"
              />
            </div>
            <div>
              <label className="text-micro font-medium text-n-300 block mb-1">
                Session Cookie (<code className="text-accent-300">li_at</code>)
              </label>
              <Input
                type="password"
                value={cookieLiAt}
                onChange={e => setCookieLiAt(e.target.value)}
                placeholder="Paste li_at cookie string..."
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <Button
              size="sm"
              variant="outline"
              busy={savingConnect}
              onClick={handleSaveLinkedIn}
            >
              Save LinkedIn Session
            </Button>
            {connectMsg && (
              <span className="text-micro text-accent-300">{connectMsg}</span>
            )}
          </div>
        </div>

        {/* Section 3: Run Discovery Scan */}
        <div className="p-4 rounded-xl border border-line bg-raised/30 space-y-3">
          <h4 className="text-tiny font-semibold text-n-100">
            Fetch Fresh Jobs from Enabled Portals
          </h4>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label className="text-micro font-medium text-n-300 block mb-1">
                Search Keywords
              </label>
              <Input
                value={keywords}
                onChange={e => setKeywords(e.target.value)}
                placeholder="e.g. Software Engineer, React, Node.js"
              />
            </div>
            <div>
              <label className="text-micro font-medium text-n-300 block mb-1">
                Target Locations
              </label>
              <Input
                value={location}
                onChange={e => setLocation(e.target.value)}
                placeholder="e.g. Pakistan, Remote"
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <Button
              variant="primary"
              busy={fetching}
              disabled={!selectedSources.length}
              onClick={handleFetch}
            >
              <Icon.Sparkles className="size-3.5 mr-1.5" />
              Scan &amp; Fetch Jobs
            </Button>

            {fetchResult && (
              <span className="text-micro text-ok-400">
                Discovered {fetchResult.found || 0} jobs ({fetchResult.saved || 0} new added to queue)
              </span>
            )}
          </div>

          {fetchError && (
            <Note tone="bad" title="Scan Notice" onDismiss={() => setFetchError('')}>
              {fetchError}
            </Note>
          )}
        </div>

        {/* Section 4: ATS Capabilities Table */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-micro font-semibold uppercase tracking-wider text-n-300">
              Supported Applicant Tracking Systems (ATS)
            </h4>
            {data && (
              <span className="text-micro text-n-400">
                {s.detects} readable · {s.proven} proven submitting
              </span>
            )}
          </div>

          {!data ? (
            <Empty title="Loading ATS capabilities..." />
          ) : (
            <Table
              columns={[{ label: 'System' }, { label: 'Finds jobs' }, { label: 'Submits' }, { label: 'Capabilities' }]}
              rows={data.rows}
              maxHeight="max-h-[22rem]"
              empty={<Empty title="No systems listed" />}
              renderRow={(p) => (
                <Tr key={p.slug}>
                  <Td className="text-n-200 font-medium">{p.name}</Td>
                  <Td>
                    {p.detects ? (
                      <Status tone="ok">yes</Status>
                    ) : (
                      <Status tone="neutral" dot={false}>
                        no public board
                      </Status>
                    )}
                  </Td>
                  <Td>
                    <Status tone={SUBMIT_TONE[p.submits] || 'neutral'} dot={p.submits === 'proven'}>
                      {SUBMIT_LABEL[p.submits] || p.submits}
                    </Status>
                  </Td>
                  <Td className="max-w-[22rem] text-tiny leading-snug text-n-500">
                    {p.note || ''}
                  </Td>
                </Tr>
              )}
            />
          )}
        </div>
      </div>
    </Disclosure>
  )
}
