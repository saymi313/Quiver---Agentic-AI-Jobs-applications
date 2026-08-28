import { useCallback, useState } from 'react'
import { api } from '../lib/api'
import { Button, Input, Note, Section } from './ui'

/*
  Paste a link and track the job into your queue.
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
      title="Track a job by URL"
      description="Paste a link from Lever, Greenhouse, Workday, or an employer's careers page to tailor a resume and apply."
    >
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-[16rem] flex-1">
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="https://jobs.lever.co/company/... or https://boards.greenhouse.io/..."
            aria-label="Job posting URL"
          />
        </div>
        <Button variant="primary" busy={busy} disabled={!url.trim()} onClick={submit}>
          Track link
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
          <Note tone="ok" title="Job added">
            {result.company ? `${result.company} — ` : ''}
            {result.title || url}
          </Note>
        </div>
      ) : null}
    </Section>
  )
}
