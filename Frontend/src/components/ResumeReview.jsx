import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion as m } from 'motion/react'
import { api } from '../lib/api'
import { springFor } from '../lib/motion'
import { Button, Note, Status, Tag, Textarea } from './ui'

/*
  The review gate: what the rewrite changed, before any of it is sent.

  Shown as a per-bullet before/after rather than a whole-document diff, because
  the unit the user actually judges is the claim in one line — "does this still
  describe what I did?" A document diff makes that question harder, not easier.

  Editing a line is expected, not exceptional, so the after-text is the input
  itself. Approving after an edit rebuilds the PDF from the edited words: the
  file on disk still carries the model's wording until it does, and approving
  text that differs from the compiled document would ship the version nobody
  read.
*/

export default function ResumeReview({ jobId, onDone, onClose }) {
  const [data, setData] = useState(null)
  const [edits, setEdits] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    api
      .agentResumeChanges(jobId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [jobId])

  const approve = useCallback(() => {
    setBusy(true)
    setError('')
    const changes = (data?.changes || []).map((c, i) => ({
      ...c,
      edited: edits[i] ?? '',
    }))
    api
      .agentApproveResume(jobId, changes)
      .then((r) => onDone?.(r))
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false))
  }, [data, edits, jobId, onDone])

  if (error && !data) {
    return (
      <Note tone="bad" title="Could not load the changes">
        {error}
      </Note>
    )
  }
  if (!data) return <p className="p-4 text-tiny text-n-500">Loading the changes…</p>

  const changes = data.changes || []
  const editedCount = Object.values(edits).filter((v) => (v || '').trim()).length

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-n-200">
          {changes.length} change{changes.length === 1 ? '' : 's'}
        </span>
        {data.mode ? <Tag>{data.mode} mode</Tag> : null}
        {data.approved === 1 ? (
          <Status tone="ok">approved</Status>
        ) : (
          <Status tone="warn">nothing sent yet</Status>
        )}
        {editedCount ? (
          <span className="text-tiny text-n-400">
            {editedCount} edited — approving rebuilds the PDF
          </span>
        ) : null}
      </div>

      {error ? (
        <Note tone="bad" title="Could not approve" onDismiss={() => setError('')}>
          {error}
        </Note>
      ) : null}

      {changes.length === 0 ? (
        <p className="text-tiny text-n-500">
          Nothing was rewritten — the curated resume went through unchanged.
        </p>
      ) : (
        <ul className="space-y-3">
          <AnimatePresence initial={false}>
            {changes.map((c, i) => (
              <m.li
                key={i}
                layout
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={springFor()}
                className="rounded-sm border border-line bg-raised p-3"
              >
                {c.field === 'summary' ? <Tag className="mb-1.5">summary</Tag> : null}
                <p className="text-tiny leading-relaxed text-n-500 line-through decoration-n-600">
                  {c.original}
                </p>
                <div className="mt-2">
                  <Textarea
                    rows={2}
                    value={edits[i] ?? c.revised}
                    onChange={(e) => setEdits((p) => ({ ...p, [i]: e.target.value }))}
                    aria-label={`Rewritten line ${i + 1}`}
                  />
                </div>
              </m.li>
            ))}
          </AnimatePresence>
        </ul>
      )}

      <div className="flex items-center gap-2">
        <Button variant="primary" busy={busy} onClick={approve} disabled={data.approved === 1}>
          {data.approved === 1 ? 'Approved' : 'Approve and use'}
        </Button>
        {onClose ? (
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        ) : null}
      </div>
    </div>
  )
}
