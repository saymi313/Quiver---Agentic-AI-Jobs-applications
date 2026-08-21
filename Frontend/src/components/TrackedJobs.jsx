import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import ResumeReview from './ResumeReview'
import { CategoryChip, SelectionBar } from './apple'
import JobFilters, { NO_FILTERS, toQuery } from './JobFilters'
import JobDetail from './JobDetail'
import { Button, Empty, Icon, Section, Status, Table, Tag, Td, Tr } from './ui'

/*
  The tracked jobs table — the centre of the Jobs screen.

  Nothing here submits on its own. An application happens only when a button
  in this table is pressed, on one row or on a selection.
*/

const STATUS = {
  applied: { tone: 'ok', label: 'applied' },
  failed: { tone: 'bad', label: 'failed' },
  matched: { tone: 'accent', label: 'ready' },
  tracked: { tone: 'accent', label: 'ready' },
  queued: { tone: 'info', label: 'queued' },
  new: { tone: 'neutral', label: 'new' },
  skipped: { tone: 'neutral', label: 'filtered out' },
  duplicate: { tone: 'neutral', label: 'duplicate' },
}

/** Rows the user cannot act on: already applied, or ruled out by the
 *  experience gate. Selecting them would let "select all" sweep up a Staff
 *  Engineer posting the agent already rejected. */
const BLOCKED = ['applied', 'skipped', 'duplicate']

const STATUS_FILTERS = [
  ['not_applied', 'Ready to apply'],
  ['applied', 'Applied'],
  ['failed', 'Failed'],
  ['skipped', 'Filtered out'],
  ['', 'All'],
]

function when(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const days = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days}d ago`
  return d.toLocaleDateString()
}

export default function TrackedJobs({ refreshKey, busy, onApply, onGenerate, toolbar }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(() => new Set())
  const [filters, setFilters] = useState(NO_FILTERS)
  const [search, setSearch] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  // Which job's rewrite is open for review, if any.
  const [reviewing, setReviewing] = useState(null)
  // Which job's detail panel is open, if any.
  const [viewing, setViewing] = useState(null)

  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => (f.q === search ? f : { ...f, q: search })), 300)
    return () => clearTimeout(t)
  }, [search])

  const load = useCallback(() => {
    let alive = true
    setLoading(true)
    api
      .agentJobs(toQuery(filters))
      .then((d) => alive && setData(d))
      .catch(() => alive && setData({ rows: [], categories: [], sources: {}, total: 0 }))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [filters])

  useEffect(() => load(), [load, refreshKey])

  const saveJob = useCallback(
    (job) => {
      const next = !job.saved
      // Reflect the bookmark at once — a toggle that waits for the network to
      // confirm feels dead, and the request rarely fails.
      setViewing((v) => (v && v.id === job.id ? { ...v, saved: next } : v))
      api.agentSaveJob(job.id, next).then(load).catch(() => {})
    },
    [load],
  )

  const passJob = useCallback(
    (job) => {
      setViewing(null)
      api.agentPassJob(job.id).then(load).catch(() => {})
    },
    [load],
  )

  const rows = data?.rows || []
  const categories = (data?.categories || []).filter((c) => c.count > 0)
  const sources = Object.entries(data?.sources || {})

  const actionable = useMemo(() => rows.filter((r) => !BLOCKED.includes(r.status)), [rows])
  const chosen = useMemo(
    () => actionable.filter((r) => selected.has(r.id)),
    [actionable, selected],
  )
  const allChecked = actionable.length > 0 && chosen.length === actionable.length

  const toggle = (id) =>
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const ids = chosen.map((r) => r.id)

  return (
    <Section
      title="Tracked jobs"
      description={
        data ? `${data.matched ?? rows.length} of ${data.total} tracked` : 'Everything the agent has found.'
      }
      flush
      actions={
        <Button size="sm" variant="ghost" onClick={load}>
          <Icon.Refresh />
          Refresh
        </Button>
      }
    >
      <JobFilters
        value={filters}
        onChange={setFilters}
        categories={categories}
        sources={sources}
        open={filtersOpen}
        onToggleOpen={setFiltersOpen}
        matched={data?.matched}
        total={data?.total}
        search={search}
        onSearch={setSearch}
      />

      {toolbar ? <div className="border-b border-line px-4 py-2.5">{toolbar}</div> : null}

      <ResumeReview
        jobId={reviewing}
        onDone={() => {
          setReviewing(null)
          load()
        }}
        onClose={() => setReviewing(null)}
      />

      <JobDetail
        job={viewing}
        busy={busy}
        onClose={() => setViewing(null)}
        onApply={(ids) => {
          setViewing(null)
          onApply(ids)
        }}
        onGenerate={onGenerate}
        onReview={(id) => {
          setViewing(null)
          setReviewing(id)
        }}
        onSave={saveJob}
        onPass={passJob}
      />

      {/* What you can do with a selection floats over the list rather than
          opening inside it, so picking a row never moves the next one. */}
      <SelectionBar open={chosen.length > 0}>
        <span className="text-tiny text-n-300">
          {chosen.length} selected
        </span>
        <Button size="sm" variant="primary" disabled={busy} onClick={() => onApply(ids)}>
          Apply
        </Button>
        <Button size="sm" disabled={busy} onClick={() => onGenerate(ids)}>
          Generate resumes
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
          Clear
        </Button>
      </SelectionBar>

      {/* ------------------------------------------------------------ table */}
      {loading && !data ? (
        <Empty title="Loading" />
      ) : (
        <Table
          columns={[
            {
              label: (
                <input
                  type="checkbox"
                  checked={allChecked}
                  onChange={() =>
                    setSelected(allChecked ? new Set() : new Set(actionable.map((r) => r.id)))
                  }
                  aria-label="Select all actionable jobs"
                  className="size-4 accent-blue-500"
                />
              ),
              className: 'w-9',
            },
            { label: 'Role', className: 'w-[24%]' },
            { label: 'Company', className: 'w-[13%]' },
            { label: 'Location', className: 'w-[12%]' },
            { label: 'Category', className: 'w-[11%]' },
            { label: 'Portal', className: 'w-[9%]' },
            { label: 'Status', className: 'w-[8%]' },
            { label: 'Found', className: 'w-[7%]' },
            { label: 'Resume', className: 'w-[9%]' },
            { label: '', className: 'w-[7%]' },
          ]}
          rows={rows}
          empty={
            <Empty title="Nothing here">
              {filters.status === 'not_applied'
                ? 'No jobs are ready to apply to. Run Find new jobs, or widen the filters.'
                : 'Try a different filter.'}
            </Empty>
          }
          renderRow={(r) => {
            const blocked = BLOCKED.includes(r.status)
            const meta = STATUS[r.status] || { tone: 'neutral', label: r.status }
            return (
              <Tr key={r.id}>
                <Td>
                  <input
                    type="checkbox"
                    disabled={blocked}
                    checked={selected.has(r.id)}
                    onChange={() => toggle(r.id)}
                    aria-label={`Select ${r.title}`}
                    className="size-4 accent-blue-500 disabled:opacity-25"
                  />
                </Td>

                <Td>
                  <span className="flex items-center gap-1.5">
                    {/* The title opens the parsed detail rather than jumping
                        straight out to the board — the panel is where the
                        salary, level and skills live, and the original posting
                        is one click further in. */}
                    <button
                      onClick={() => setViewing(r)}
                      className="press text-left text-sm font-medium text-n-100 hover:text-blue-500"
                    >
                      {r.title}
                    </button>
                    <button
                      onClick={() => saveJob(r)}
                      aria-pressed={r.saved}
                      aria-label={r.saved ? 'Remove bookmark' : 'Save job'}
                      title={r.saved ? 'Saved' : 'Save'}
                      className={`press shrink-0 rounded p-0.5 ${
                        r.saved ? 'text-blue-500' : 'text-n-400 hover:text-n-200'
                      }`}
                    >
                      <Icon.Bookmark filled={r.saved} className="size-3.5" />
                    </button>
                  </span>
                  {r.fit_score ? (
                    <span className="text-micro text-n-500">{Math.round(r.fit_score)}</span>
                  ) : null}
                  {/* Why this score, on every row rather than only on the ones
                      that were filtered out. A number with no reasoning behind
                      it is not something anyone can act on. */}
                  {r.fit_reason ? (
                    <p
                      className="mt-1 line-clamp-2 text-micro leading-snug text-n-500"
                      title={r.fit_reason}
                    >
                      {r.fit_reason}
                    </p>
                  ) : null}
                  {r.failure_reason ? (
                    <p className="mt-1 line-clamp-2 text-micro leading-snug text-bad-400">
                      {r.failure_reason}
                      {r.screenshot ? (
                        <>
                          {' '}
                          <a
                            href={api.agentScreenshotUrl(r.screenshot)}
                            target="_blank"
                            rel="noreferrer"
                            className="text-n-500 underline hover:text-n-300"
                          >
                            screenshot
                          </a>
                        </>
                      ) : null}
                    </p>
                  ) : null}
                </Td>

                {/* Some boards put a whole paragraph in the company field. */}
                <Td className="max-w-[11rem] truncate text-n-400" title={r.company_name || ''}>
                  {r.company_name || '—'}
                </Td>

                {/* Boards write location as anything from "Remote" to a list
                    of nine countries, so it truncates with the full text on
                    hover rather than wrapping the row to three lines. */}
                <Td className="max-w-[13rem] text-n-400" title={r.location || ''}>
                  <span className="block truncate">{r.location || (r.remote ? 'Remote' : '—')}</span>
                  {r.remote && r.location ? (
                    <span className="text-micro text-n-500">Remote</span>
                  ) : null}
                </Td>
                <Td>
                  <CategoryChip slug={r.role_category} />
                </Td>
                <Td className="text-n-500">{r.source || '—'}</Td>

                <Td>
                  <Status tone={meta.tone} title={r.status === 'skipped' ? r.fit_reason : ''}>
                    {meta.label}
                  </Status>
                </Td>

                <Td className="whitespace-nowrap text-n-500">{when(r.discovered_at)}</Td>

                <Td>
                  {r.has_resume ? (
                    <span className="flex items-center gap-2">
                      <a
                        href={api.agentResumeUrl(r.id, 'pdf')}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-500 hover:underline"
                        title={r.resume_version || ''}
                      >
                        view
                      </a>
                      {/* An unapproved rewrite is the one thing standing
                          between this job and an application, so it is a
                          call to action rather than a badge. */}
                      {r.resume_approved === 0 ? (
                        <button
                          onClick={() => setReviewing(r.id)}
                          className="press text-warn-400 hover:underline"
                        >
                          review
                        </button>
                      ) : null}
                    </span>
                  ) : (
                    <button
                      disabled={busy}
                      onClick={() => onGenerate([r.id])}
                      className="press text-blue-500 hover:underline disabled:opacity-40"
                    >
                      generate
                    </button>
                  )}
                </Td>

                <Td className="text-right">
                  {blocked ? null : (
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => onApply([r.id])}>
                      Apply
                    </Button>
                  )}
                </Td>
              </Tr>
            )
          }}
        />
      )}
    </Section>
  )
}
