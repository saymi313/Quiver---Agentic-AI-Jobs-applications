import { useCallback, useState } from 'react'
import { api } from '../lib/api'
import { Button, Icon, Input, Note, Section } from './ui'
import FetchPortalsModal from './FetchPortalsModal'

/*
  Paste a link, track the job, or fetch directly from live portals (LinkedIn, etc.)
*/
export default function AddJobByUrl({ onAdded }) {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [showPortalsModal, setShowPortalsModal] = useState(false)

  const submit = useCallback(() => {
    if (!url.trim()) return
    setBusy(true)
    setError('')
    setResult(null)
    api
      .agentJobFromUrl(url.trim())
      .then((r) => {
        setResult(r)
        setUrl('')
        onAdded?.()
      })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false))
  }, [url, onAdded])

  return (
    <Section
      title="Add or Discover Jobs"
      description="Paste any posting URL, or fetch live verified roles from LinkedIn, WeWorkRemotely, and Jobicy."
    >
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-[16rem] flex-1">
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="https://jobs.lever.co/company/... or https://www.linkedin.com/jobs/view/..."
            aria-label="Job posting URL"
          />
        </div>
        <Button variant="primary" busy={busy} disabled={!url.trim()} onClick={submit}>
          Track link
        </Button>
        <Button
          variant="outline"
          onClick={() => setShowPortalsModal(true)}
          className="border-accent-500/40 text-accent-300 hover:bg-accent-950/30"
        >
          <Icon.Sparkles className="size-3.5 mr-1.5" />
          Fetch from Portals (LinkedIn, Remote)
        </Button>
      </div>

      <FetchPortalsModal
        isOpen={showPortalsModal}
        onClose={() => setShowPortalsModal(false)}
        onFetched={onAdded}
      />

      {error ? (
        <div className="mt-3">
          <Note tone="bad" title="Could not read that posting" onDismiss={() => setError('')}>
            {error}
          </Note>
        </div>
      ) : null}

      {result ? (
        <div className="mt-3">
          <Note
            tone={result.created ? 'ok' : 'info'}
            title={result.created ? 'Tracked' : 'Already tracked'}
            onDismiss={() => setResult(null)}
          >
            {result.title}
            {result.company ? ` at ${result.company}` : ''}
            {result.fitScore ? ` · scored ${Math.round(result.fitScore)}` : ''}
            {result.fitReason ? ` — ${result.fitReason}` : ''}
          </Note>
        </div>
      ) : null}
    </Section>
  )
}
