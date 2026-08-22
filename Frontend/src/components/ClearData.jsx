import { useState } from 'react'
import { api } from '../lib/api'
import { Sheet } from './apple'
import { Button, Checkbox, Note } from './ui'

/*
  Emptying a table, safely.

  A destructive action gets a confirmation because it cannot be taken back from
  the live database — but the confirmation is honest about what survives it: the
  server writes a JSON snapshot before it deletes anything, so this is recoverable
  from disk even though the app offers no undo button. The jobs variant keeps the
  roles you applied to and the ones you saved by default, because losing your own
  history is not what "clear the list" means.
*/

export default function ClearData({ kind, onCleared }) {
  const [open, setOpen] = useState(false)
  const [keepApplied, setKeepApplied] = useState(true)
  const [keepSaved, setKeepSaved] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(null)

  const isJobs = kind === 'jobs'

  const run = () => {
    setBusy(true)
    setError('')
    const call = isJobs ? api.agentClearJobs({ keepApplied, keepSaved }) : api.agentClearTracker()
    call
      .then((r) => {
        setDone(r)
        onCleared?.()
      })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false))
  }

  const close = () => {
    setOpen(false)
    setDone(null)
    setError('')
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="press text-tiny text-n-500 hover:text-bad-400"
      >
        {isJobs ? 'Clear jobs' : 'Clear tracker'}
      </button>

      <Sheet
        open={open}
        onClose={close}
        title={isJobs ? 'Clear the jobs table?' : 'Clear the tracker?'}
        description={
          isJobs
            ? 'Removes discovered roles. Backed up to disk first — this cannot be undone in the app.'
            : 'Removes every application and inbox message. Backed up to disk first — this cannot be undone in the app.'
        }
        footer={
          done ? (
            <Button variant="primary" onClick={close}>Done</Button>
          ) : (
            <div className="flex items-center gap-2">
              <Button variant="primary" busy={busy} onClick={run}>
                {isJobs ? 'Clear jobs' : 'Clear tracker'}
              </Button>
              <Button variant="ghost" onClick={close}>Cancel</Button>
            </div>
          )
        }
      >
        {error ? (
          <Note tone="bad" title="Could not clear" onDismiss={() => setError('')}>{error}</Note>
        ) : done ? (
          <Note tone="ok" title="Cleared">
            {isJobs
              ? `Deleted ${done.deleted} job${done.deleted === 1 ? '' : 's'}${
                  done.kept ? `, kept ${done.kept}` : ''
                }. Backup: ${done.backup}`
              : `Deleted ${done.applications} application${done.applications === 1 ? '' : 's'} and ${
                  done.messages
                } message${done.messages === 1 ? '' : 's'}.`}
          </Note>
        ) : isJobs ? (
          <div className="space-y-3">
            <Checkbox
              checked={keepApplied}
              onChange={setKeepApplied}
              label="Keep jobs I applied to"
              hint="Protects the roles behind your tracker — losing those is not housekeeping."
            />
            <Checkbox
              checked={keepSaved}
              onChange={setKeepSaved}
              label="Keep bookmarked jobs"
              hint="The shortlist you built by hand."
            />
            <p className="text-tiny leading-relaxed text-n-500">
              Everything else in the jobs table is removed. Run “Find new jobs” to repopulate — and
              because the dedupe hashes clear too, previously-seen roles come in fresh rather than
              being skipped as duplicates.
            </p>
          </div>
        ) : (
          <p className="text-tiny leading-relaxed text-n-400">
            The pipeline and the inbox both empty. Your mailbox is untouched — press “Read replies”
            afterwards to re-pull matching mail.
          </p>
        )}
      </Sheet>
    </>
  )
}
