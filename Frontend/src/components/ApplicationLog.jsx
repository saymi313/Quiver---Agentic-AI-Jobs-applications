import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { Button, Disclosure, Input, Note, Status } from './ui'

/* ------------------------------------------------------- application log */

const APP_TONE = {
  submitted: 'ok', filled: 'info', failed: 'bad', skipped: 'warn',
  running: 'accent', queued: 'info', needs_review: 'warn',
}

// A friendlier word than the machine status for the two in-flight states.
const IN_FLIGHT = { running: 'applying', queued: 'queued' }

// What a needs-review row is actually waiting for, read from its reason. A form
// held for approval, a one-time code the site sent, or a question the profile
// could not answer — each wants a different next step.
function waitingFor(r) {
  if (r.status !== 'needs_review') return null
  const e = (r.error || '').toLowerCase()
  if (/one[- ]time|\bcode\b/.test(e)) return 'otp'
  if (/review|approve to submit/.test(e)) return 'review'
  return 'other'
}

export default function ApplicationLog({ refreshKey, onApprove }) {
  const [rows, setRows] = useState([])
  const [open, setOpen] = useState(false)
  const [otpFor, setOtpFor] = useState(null) // job id whose code box is open
  const [code, setCode] = useState('')
  const [saved, setSaved] = useState(null)

  useEffect(() => {
    api
      .agentData('applications', 40)
      .then((d) => setRows(d.rows))
      .catch(() => setRows([]))
  }, [refreshKey])

  const summary = useMemo(() => {
    const real = rows.filter((r) => !r.dry_run)
    const sent = real.filter((r) => r.status === 'submitted').length
    return `${sent} submitted · ${real.length - sent} failed · ${rows.length - real.length} dry run`
  }, [rows])

  const submitCode = (jobId) =>
    api.agentSubmitOtp(jobId, code.trim()).then(() => {
      setSaved(jobId)
      setOtpFor(null)
      setCode('')
    }).catch(() => {})

  return (
    <Disclosure
      title="Application history"
      description={rows.length ? summary : 'No attempts yet.'}
      open={open}
      onToggle={setOpen}
    >
      {rows.length === 0 ? (
        <p className="text-tiny text-n-500">Nothing yet. Apply to a job above and it appears here.</p>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((r) => {
            const wait = waitingFor(r)
            return (
              <li key={r.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1.5 py-2 first:pt-0">
                {/* An application still in flight pulses, so a run in progress
                    reads at a glance rather than only in the console. */}
                <Status tone={APP_TONE[r.status] || 'neutral'} pulse={r.status === 'running'}>
                  {IN_FLIGHT[r.status] || r.status}
                </Status>
                <span className="text-sm text-n-200">{r.title || 'Unknown role'}</span>
                <span className="text-tiny text-n-500">{r.company_name || ''}</span>
                {r.dry_run ? <span className="text-micro text-n-500">dry run</span> : null}

                {/* the action a needs-review row is waiting on */}
                {wait === 'review' && r.job_id ? (
                  <Button size="sm" variant="primary" className="ml-auto"
                          onClick={() => onApprove?.(r.job_id)}>
                    Approve &amp; submit
                  </Button>
                ) : wait === 'otp' && r.job_id ? (
                  saved === r.job_id ? (
                    <span className="ml-auto text-micro text-ok-400">
                      code saved — apply again to use it
                    </span>
                  ) : otpFor === r.job_id ? (
                    <span className="ml-auto flex items-center gap-1.5">
                      <div className="w-28">
                        <Input value={code} onChange={(e) => setCode(e.target.value)}
                               placeholder="code" aria-label="One-time code" className="h-7 py-0" />
                      </div>
                      <Button size="sm" variant="primary" disabled={!code.trim()}
                              onClick={() => submitCode(r.job_id)}>
                        Save
                      </Button>
                    </span>
                  ) : (
                    <Button size="sm" className="ml-auto" onClick={() => { setOtpFor(r.job_id); setCode('') }}>
                      Enter code
                    </Button>
                  )
                ) : null}

                {r.error ? (
                  <span className="w-full text-tiny leading-relaxed text-n-500">{r.error}</span>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}

      {saved ? (
        <div className="mt-3">
          <Note tone="ok" title="Code saved" onDismiss={() => setSaved(null)}>
            Apply to that job again and the code will be entered for you.
          </Note>
        </div>
      ) : null}
    </Disclosure>
  )
}
