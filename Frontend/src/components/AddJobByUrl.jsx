import { useCallback, useState } from 'react'
import { api } from '../lib/api'
import { Button, Input, Note, Section } from './ui'

/*
  Paste a link, track the job.

  Discovery finds roles the agent went looking for; this is for the one a
  friend sent you. Same pipeline from the URL onwards — fetch the description,
  classify the role, score it against the profile — so the row that appears is
  indistinguishable from a discovered one.
*/
export default function AddJobByUrl({ onAdded }) {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

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
      title="Add a job by link"
      description="Paste any posting URL. Jobenzy reads it, works out the role and scores it like any other."
    >
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-[16rem] flex-1">
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="https://jobs.lever.co/company/..."
            aria-label="Job posting URL"
          />
        </div>
        <Button variant="primary" busy={busy} disabled={!url.trim()} onClick={submit}>
          Track it
        </Button>
      </div>

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
