import { useEffect, useMemo, useState } from 'react'
import { motion as m } from 'motion/react'
import { api } from '../lib/api'
import { springFor } from '../lib/motion'
import { CategoryChip, ScoreRing, SidePanel } from '../components/apple'
import { Empty, Icon, Input, PageHead, Status } from '../components/ui'

/*
  Research — what is known about the companies you are applying to.

  Everything here Quiver already gathered on the way to finding a role: the
  company's own facts, the founders and recruiters whose addresses were verified,
  and every posting seen there. Pulled into one place, it is what you read before
  an interview or before writing to someone — the difference between "I applied"
  and "I know who you are".

  Grounded, not generated: every line traces to something discovered, so there is
  nothing here to be wrong about. A company with nothing known simply does not
  appear.
*/

const REGION = { us: 'US', eu: 'Europe', remote: 'Remote-first', pk: 'Pakistan', other: '' }

export default function ResearchTab() {
  const [rows, setRows] = useState(null)
  const [q, setQ] = useState('')
  const [openId, setOpenId] = useState(null)

  useEffect(() => {
    let alive = true
    api.agentResearch().then((d) => alive && setRows(d.rows || [])).catch(() => alive && setRows([]))
    return () => { alive = false }
  }, [])

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return rows || []
    return (rows || []).filter((c) =>
      `${c.name} ${c.industry || ''} ${c.location || ''}`.toLowerCase().includes(needle))
  }, [rows, q])

  if (rows === null) return <Empty title="Loading" />

  return (
    <div className="space-y-4">
      <PageHead
        title="Research"
        description="What Quiver already knows about the companies behind your roles — facts, contacts and every posting seen there. Grounded in what was found, not generated."
      />

      {rows.length === 0 ? (
        <Empty title="Nothing to research yet">
          Companies appear here once the agent has found roles at them. Run a search from the
          dashboard first.
        </Empty>
      ) : (
        <>
          <div className="max-w-sm">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search companies"
                   aria-label="Search companies" />
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {shown.map((c, i) => (
              <m.button
                key={c.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...springFor(), delay: Math.min(i, 8) * 0.03 }}
                onClick={() => setOpenId(c.id)}
                className="press flex flex-col rounded-md border border-line bg-surface p-4 text-left
                  hover:border-line-strong"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-n-100">{c.name}</p>
                    <p className="truncate text-micro text-n-500">
                      {c.industry || c.domain || REGION[c.region] || '—'}
                    </p>
                  </div>
                  {c.ats_platform ? <Status tone="neutral" dot={false}>{c.ats_platform}</Status> : null}
                </div>
                {c.location ? <p className="mt-2 truncate text-micro text-n-400">{c.location}</p> : null}
                <div className="mt-3 flex items-center gap-3 text-micro text-n-500">
                  <span className="tabular-nums">{c.job_count} role{c.job_count === 1 ? '' : 's'}</span>
                  {c.contact_count ? (
                    <span className="tabular-nums">{c.contact_count} contact{c.contact_count === 1 ? '' : 's'}</span>
                  ) : null}
                </div>
              </m.button>
            ))}
          </div>
        </>
      )}

      <CompanyPanel id={openId} onClose={() => setOpenId(null)} />
    </div>
  )
}

function CompanyPanel({ id, onClose }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    if (!id) { setData(null); return }
    let alive = true
    setData(null)
    api.agentResearchCompany(id).then((d) => alive && setData(d)).catch(() => alive && setData({}))
    return () => { alive = false }
  }, [id])

  const c = data?.company
  const people = data?.people || []
  const jobs = data?.jobs || []

  return (
    <SidePanel
      open={!!id}
      onClose={onClose}
      title={c?.name || 'Loading…'}
      subtitle={c ? c.industry || c.domain || undefined : undefined}
      badge={
        c ? (
          <div className="flex flex-wrap items-center gap-2">
            {c.region ? <Status tone="neutral" dot={false}>{REGION[c.region] || c.region}</Status> : null}
            {c.ats_platform ? <span className="text-micro text-n-500">{c.ats_platform}</span> : null}
          </div>
        ) : null
      }
    >
      {!data ? (
        <p className="text-tiny text-n-500">Loading…</p>
      ) : !c ? (
        <p className="text-tiny text-n-500">Nothing found for that company.</p>
      ) : (
        <div className="space-y-5">
          {c.description ? (
            <p className="text-tiny leading-relaxed text-n-300">{c.description}</p>
          ) : null}

          {/* facts */}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 border-y border-line py-4 text-tiny">
            {[
              ['Website', c.website || c.domain, c.website || (c.domain && `https://${c.domain}`)],
              ['Location', c.location],
              ['Team size', c.team_size],
              ['Founded', c.founded],
            ].map(([label, value, href]) =>
              value ? (
                <div key={label}>
                  <dt className="text-micro tracking-wide text-n-500 uppercase">{label}</dt>
                  <dd className="truncate text-n-100">
                    {href ? (
                      <a href={href} target="_blank" rel="noreferrer" className="text-blue-500 hover:underline">
                        {value}
                      </a>
                    ) : value}
                  </dd>
                </div>
              ) : null,
            )}
          </dl>

          {/* contacts */}
          {people.length ? (
            <div>
              <p className="pb-2 text-micro font-medium tracking-wide text-n-500 uppercase">
                Contacts ({people.length})
              </p>
              <ul className="space-y-2">
                {people.map((p) => (
                  <li key={p.id} className="flex items-center gap-3 rounded-sm border border-line
                    bg-raised px-3 py-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-n-100">{p.full_name || p.email}</p>
                      <p className="truncate text-micro text-n-500">
                        {[p.title || p.role, p.email].filter(Boolean).join(' · ')}
                      </p>
                    </div>
                    <Status tone={p.email_status === 'valid' ? 'ok' : p.email_status === 'risky' ? 'warn' : 'neutral'}
                            dot={false}>
                      {p.email_status || 'unknown'}
                    </Status>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {/* roles seen here */}
          <div>
            <p className="pb-2 text-micro font-medium tracking-wide text-n-500 uppercase">
              Roles seen here ({jobs.length})
            </p>
            <ul className="space-y-2">
              {jobs.map((j) => (
                <li key={j.id} className="flex items-center gap-3 rounded-sm border border-line px-3 py-2">
                  {j.fit_score ? <ScoreRing value={j.fit_score} size={34} stroke={3} /> : null}
                  <div className="min-w-0 flex-1">
                    <a href={j.url} target="_blank" rel="noreferrer"
                       className="block truncate text-sm text-n-100 hover:text-blue-500">
                      {j.title}
                    </a>
                    <p className="truncate text-micro text-n-500">
                      {j.location || (j.remote ? 'Remote' : '')}
                    </p>
                  </div>
                  <CategoryChip slug={j.role_category} />
                </li>
              ))}
            </ul>
          </div>

          {c.careers_url ? (
            <a href={c.careers_url} target="_blank" rel="noreferrer"
               className="press inline-flex items-center gap-1.5 text-tiny text-blue-500 hover:underline">
              <Icon.Doc className="size-3.5" />
              Careers page
            </a>
          ) : null}
        </div>
      )}
    </SidePanel>
  )
}
