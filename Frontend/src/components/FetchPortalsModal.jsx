import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Button, Icon, Input, Status } from './ui'

/*
  Fetch from Public Portals (LinkedIn, WeWorkRemotely, Jobicy)
  and Connect LinkedIn Profile. Zero emojis, pure Apple aesthetic.
*/

export default function FetchPortalsModal({ isOpen, onClose, onFetched }) {
  const [sources, setSources] = useState([])
  const [selectedSources, setSelectedSources] = useState(['linkedin', 'weworkremotely', 'jobicy'])
  const [keywords, setKeywords] = useState('Software Engineer, Full Stack, React, Node.js')
  const [location, setLocation] = useState('Pakistan, Remote')
  const [limit, setLimit] = useState(20)
  const [fetching, setFetching] = useState(false)
  const [fetchResult, setFetchResult] = useState(null)
  const [fetchError, setFetchError] = useState('')

  // LinkedIn connection
  const [profileUrl, setProfileUrl] = useState('')
  const [cookieLiAt, setCookieLiAt] = useState('')
  const [connected, setConnected] = useState(false)
  const [savingConnect, setSavingConnect] = useState(false)
  const [connectMsg, setConnectMsg] = useState('')

  useEffect(() => {
    if (!isOpen) return
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
  }, [isOpen])

  if (!isOpen) return null

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
        setConnectMsg('LinkedIn profile connected successfully.')
      } else {
        setConnectMsg('Profile details saved.')
      }
    } catch (err) {
      setConnectMsg(err.message || 'Could not save connection.')
    } finally {
      setSavingConnect(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-2xl bg-surface border border-line rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-line flex items-center justify-between bg-surface-sunken/40">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-micro font-semibold uppercase tracking-wider text-accent-400">
                Live Portals &amp; Integrations
              </span>
              <span className="text-micro text-n-500">Pakistan &amp; Global Remote</span>
            </div>
            <h2 className="text-sm font-semibold text-n-100 mt-0.5">
              Discover Jobs from LinkedIn, WeWorkRemotely &amp; Tech Boards
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="press p-1 text-n-400 hover:text-n-100 rounded hover:bg-raised transition-colors"
            title="Close"
          >
            <Icon.X className="size-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto flex-1 space-y-5">
          {/* Portals Selection */}
          <div className="space-y-2.5">
            <label className="text-micro font-semibold uppercase tracking-wider text-n-300 block">
              Active Job Sources
            </label>
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
                        : 'bg-raised/50 border-line text-n-400 hover:border-line-strong'
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
                      active ? 'bg-accent-500 border-accent-500 text-white' : 'border-line-strong'
                    }`}>
                      {active && <Icon.Check className="size-3" />}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Search Filters */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-micro font-semibold uppercase tracking-wider text-n-400 block mb-1">
                Target Keywords
              </label>
              <Input
                value={keywords}
                onChange={e => setKeywords(e.target.value)}
                placeholder="Software Engineer, Full Stack, React"
              />
            </div>
            <div>
              <label className="text-micro font-semibold uppercase tracking-wider text-n-400 block mb-1">
                Locations
              </label>
              <Input
                value={location}
                onChange={e => setLocation(e.target.value)}
                placeholder="Pakistan, Remote, Karachi, Lahore"
              />
            </div>
          </div>

          {/* Fetch Action */}
          <div className="pt-1 flex items-center justify-between border-t border-line/60">
            <div className="text-micro text-n-400">
              Direct live sync into tracked jobs table with ATS scoring.
            </div>
            <Button
              variant="primary"
              busy={fetching}
              disabled={selectedSources.length === 0}
              onClick={handleFetch}
            >
              Fetch Live Jobs
            </Button>
          </div>

          {/* Results feedback */}
          {fetchError && (
            <div className="p-3 bg-bad-950/30 border border-bad-500/30 rounded-lg text-bad-400 text-tiny">
              {fetchError}
            </div>
          )}

          {fetchResult && (
            <div className="p-3.5 bg-ok-950/30 border border-ok-500/30 rounded-lg text-tiny space-y-1">
              <div className="font-semibold text-ok-300 flex items-center gap-1.5">
                <Icon.Check className="size-4" />
                <span>Successfully added {fetchResult.added} new jobs ({fetchResult.scored?.scored || 0} scored)!</span>
              </div>
              <p className="text-n-300 text-micro">
                Sources queried: {fetchResult.sources.join(', ')}. Check your Tracked Jobs table to review and generate resumes.
              </p>
            </div>
          )}

          {/* Connect LinkedIn Profile Section */}
          <div className="mt-4 p-4 bg-raised/70 border border-line rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-tiny font-semibold text-n-100">
                  Connect LinkedIn Account
                </h4>
                <p className="text-micro text-n-400 mt-0.5">
                  Link your LinkedIn profile URL or session cookie to personalize recommendations and applications.
                </p>
              </div>
              {connected && <Status tone="ok">Connected</Status>}
            </div>

            <div className="space-y-2 pt-1">
              <Input
                value={profileUrl}
                onChange={e => setProfileUrl(e.target.value)}
                placeholder="https://linkedin.com/in/your-profile"
                aria-label="LinkedIn profile URL"
              />
              <Input
                value={cookieLiAt}
                onChange={e => setCookieLiAt(e.target.value)}
                placeholder="Session Cookie (li_at) — optional for authenticated sync"
                type="password"
                aria-label="LinkedIn session cookie"
              />
            </div>

            <div className="flex items-center justify-between pt-1">
              <span className="text-micro text-n-500">
                {connectMsg || 'Cookie is securely stored locally in your profile settings.'}
              </span>
              <Button
                variant="outline"
                busy={savingConnect}
                onClick={handleSaveLinkedIn}
              >
                Save Connection
              </Button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3.5 border-t border-line flex items-center justify-end bg-surface-sunken/40">
          <Button variant="ghost" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>
    </div>
  )
}
