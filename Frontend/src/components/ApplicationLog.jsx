import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { Disclosure, Status } from './ui'

/* ------------------------------------------------------- application log */

const APP_TONE = { submitted: 'ok', filled: 'info', failed: 'bad', skipped: 'warn' }

export default function ApplicationLog({ refreshKey }) {
  const [rows, setRows] = useState([])
  const [open, setOpen] = useState(false)

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
          {rows.map((r) => (
            <li key={r.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2 first:pt-0">
              <Status tone={APP_TONE[r.status] || 'neutral'}>{r.status}</Status>
              <span className="text-sm text-n-200">{r.title || 'Unknown role'}</span>
              <span className="text-tiny text-n-500">{r.company_name || ''}</span>
              {r.dry_run ? <span className="text-micro text-n-500">dry run</span> : null}
              {r.error ? (
                <span className="w-full text-tiny leading-relaxed text-n-500">{r.error}</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Disclosure>
  )
}
