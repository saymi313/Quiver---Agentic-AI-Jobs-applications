import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion as m } from 'motion/react'
import { api } from '../lib/api'
import { springFor } from '../lib/motion'
import ResumeReview from './ResumeReview'
import { CategoryChip, ScoreRing, SelectionBar } from './apple'
import JobFilters, { NO_FILTERS, toQuery } from './JobFilters'
import JobDetail from './JobDetail'
import { OutreachModal } from './OutreachModal'
import { AtsAuditModal } from './AtsAuditModal'
import { InterviewPrepModal } from './InterviewPrepModal'
import ClearData from './ClearData'
import { Button, Empty, Icon, Section, Status, Table, Tag, Td, Tr } from './ui'

/*
  The tracked jobs table & cards view — the centre of the Jobs screen.

  Nothing here submits on its own. An application happens only when a button
  in this table or card is pressed, on one row or on a selection.
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

const TINTS = ['bg-tint-1', 'bg-tint-2', 'bg-tint-3', 'bg-tint-4']
const CUR = { USD: '$', GBP: '£', EUR: '€', JPY: '¥', INR: '₹' }

function salaryHint(job) {
  const { salary_min: lo, salary_max: hi, salary_currency: cur } = job
  const sym = CUR[cur] || (cur ? `${cur} ` : '')
  const k = (n) => `${Math.round(n / 1000)}k`
  if (lo != null && hi != null) return `${sym}${k(lo)}–${k(hi)}`
  if (lo != null || hi != null) return `${sym}${k(lo ?? hi)}`
  return null
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

function fitScoreTone(score) {
  if (!score && score !== 0) return 'neutral'
  if (score >= 80) return 'ok'
  if (score >= 65) return 'accent'
  if (score >= 50) return 'neutral'
  return 'bad'
}

function FitScoreBadge({ score, reason, onClick }) {
  if (score == null || isNaN(score) || score === 0) {
    return <span className="text-micro font-medium text-n-600">—</span>
  }
  const s = Math.round(score)
  const tone = fitScoreTone(s)
  return (
    <div
      onClick={onClick}
      className={`inline-flex items-center gap-1 ${onClick ? 'cursor-pointer hover:opacity-85' : ''}`}
      title={reason || `Fit score: ${s}% (Click for ATS Keyword Audit)`}
    >
      <span
        className={`inline-flex items-center justify-center rounded-full px-2.5 py-0.5 text-micro font-semibold tabular-nums tracking-wide ${
          tone === 'ok'
            ? 'bg-ok-900/40 text-ok-400 border border-ok-500/30'
            : tone === 'accent'
            ? 'bg-blue-900/40 text-blue-400 border border-blue-500/30'
            : tone === 'neutral'
            ? 'bg-n-800 text-n-300 border border-line'
            : 'bg-bad-900/40 text-bad-400 border border-bad-500/30'
        }`}
      >
        {s}%
      </span>
    </div>
  )
}

export default function TrackedJobs({ refreshKey, busy, onApply, onGenerate, toolbar }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(() => new Set())
  const [filters, setFilters] = useState(NO_FILTERS)
  const [search, setSearch] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [viewMode, setViewMode] = useState(() => localStorage.getItem('jobenzy_jobs_view') || 'table')
  // Which job's rewrite is open for review, if any.
  const [reviewing, setReviewing] = useState(null)
  // Which job's detail panel is open, if any.
  const [viewing, setViewing] = useState(null)
  // AI & Outreach Intelligence Modals
  const [outreachJob, setOutreachJob] = useState(null)
  const [atsAuditJob, setAtsAuditJob] = useState(null)
  const [interviewPrepJob, setInterviewPrepJob] = useState(null)

  const handleSetViewMode = (mode) => {
    setViewMode(mode)
    localStorage.setItem('jobenzy_jobs_view', mode)
  }

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
        <div className="flex items-center gap-3">
          {/* Table / Cards View Switcher */}
          <div className="inline-flex items-center rounded-md border border-line bg-surface-sunken p-0.5">
            <button
              onClick={() => handleSetViewMode('table')}
              className={`press inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-tiny font-medium transition-all ${
                viewMode === 'table'
                  ? 'bg-surface text-n-100 shadow-2xs border border-line'
                  : 'text-n-400 hover:text-n-200'
              }`}
              title="Table View"
            >
              <Icon.List className="size-3.5" />
              <span>Table</span>
            </button>
            <button
              onClick={() => handleSetViewMode('cards')}
              className={`press inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-tiny font-medium transition-all ${
                viewMode === 'cards'
                  ? 'bg-surface text-n-100 shadow-2xs border border-line'
                  : 'text-n-400 hover:text-n-200'
              }`}
              title="Cards View"
            >
              <Icon.Grid className="size-3.5" />
              <span>Cards</span>
            </button>
          </div>
          <ClearData kind="jobs" onCleared={load} />
          <Button size="sm" variant="ghost" onClick={load}>
            <Icon.Refresh />
            Refresh
          </Button>
        </div>
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

      {/* ------------------------------------------------------------ Table or Cards View */}
      {loading && !data ? (
        <Empty title="Loading" />
      ) : rows.length === 0 ? (
        <Empty title="Nothing here">
          {filters.status === 'not_applied'
            ? 'No jobs are ready to apply to. Run Find new jobs, or widen the filters.'
            : 'Try a different filter.'}
        </Empty>
      ) : viewMode === 'cards' ? (
        <div className="p-5 space-y-4">
          {/* Card View Bulk Select Bar */}
          <div className="flex items-center justify-between border-b border-line pb-3">
            <label className="flex items-center gap-2 text-xs font-medium text-n-300 cursor-pointer">
              <input
                type="checkbox"
                checked={allChecked}
                onChange={() =>
                  setSelected(allChecked ? new Set() : new Set(actionable.map((r) => r.id)))
                }
                aria-label="Select all actionable jobs"
                className="size-4 accent-blue-500"
              />
              <span>Select all actionable ({actionable.length})</span>
            </label>
            <span className="text-micro text-n-500">
              Showing {rows.length} {rows.length === 1 ? 'job' : 'jobs'}
            </span>
          </div>

          {/* Cards Grid — Apple Top Matches Style */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {rows.map((r, idx) => {
              const blocked = BLOCKED.includes(r.status)
              const meta = STATUS[r.status] || { tone: 'neutral', label: r.status }
              const isSelected = selected.has(r.id)

              return (
                <m.article
                  key={r.id}
                  layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={springFor()}
                  className={`rounded-xl border bg-surface flex flex-col justify-between transition-all duration-150 overflow-hidden shadow-2xs ${
                    isSelected
                      ? 'border-blue-500/60 ring-1 ring-blue-500/30'
                      : 'border-line hover:border-n-600 hover:shadow-xs'
                  }`}
                >
                  {/* Card Header with Apple subtle tint and ScoreRing */}
                  <div className={`p-4 border-b border-line/60 ${TINTS[idx % TINTS.length]}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-2.5 min-w-0 flex-1">
                        <input
                          type="checkbox"
                          disabled={blocked}
                          checked={isSelected}
                          onChange={() => toggle(r.id)}
                          aria-label={`Select ${r.title}`}
                          className="mt-1 size-4 accent-blue-500 disabled:opacity-25 shrink-0"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-micro font-medium tracking-wide text-n-400 uppercase" title={r.company_name}>
                            {r.company_name || 'Unknown Company'}
                          </p>
                          <h3
                            onClick={() => setViewing(r)}
                            className="press mt-0.5 text-sm font-semibold text-n-100 hover:text-blue-400 line-clamp-2 cursor-pointer leading-snug"
                            title={r.title}
                          >
                            {r.title}
                          </h3>
                          {salaryHint(r) ? (
                            <p className="mt-1 text-micro font-medium text-n-200">
                              {salaryHint(r)}
                            </p>
                          ) : r.location ? (
                            <p className="mt-1 truncate text-micro text-n-400">
                              {r.location} {r.remote ? '· Remote' : ''}
                            </p>
                          ) : null}
                        </div>
                      </div>

                      {/* ScoreRing from Apple kit */}
                      <div className="shrink-0 flex flex-col items-center gap-0.5 pl-1">
                        <ScoreRing value={r.fit_score} size={42} />
                        <span className="text-[9px] font-medium text-n-400 uppercase tracking-wider">Score</span>
                      </div>
                    </div>

                    {/* Category Chip & Location & Portal */}
                    <div className="flex flex-wrap items-center gap-1.5 mt-3 pt-2 border-t border-line/40">
                      <CategoryChip slug={r.role_category} />
                      {r.source ? (
                        <span className="rounded-full border border-line bg-surface-sunken px-2 py-0.5 text-micro text-n-400">
                          {r.source}
                        </span>
                      ) : null}
                      <span className="ml-auto text-micro text-n-500">{when(r.discovered_at)}</span>
                    </div>
                  </div>

                  {/* Card Middle: Match summary & JD preview link */}
                  <div className="p-4 space-y-3 flex-1 flex flex-col justify-between">
                    {r.fit_reason ? (
                      <p className="text-micro leading-relaxed text-n-400 line-clamp-2" title={r.fit_reason}>
                        <strong className="font-semibold text-n-300">Match summary: </strong>
                        {r.fit_reason}
                      </p>
                    ) : null}

                    {r.failure_reason ? (
                      <p className="text-micro leading-relaxed text-bad-400 line-clamp-2">
                        {r.failure_reason}
                      </p>
                    ) : null}

                    {/* Preview JD & Intelligence Action Buttons */}
                    <div className="pt-1 flex flex-wrap items-center gap-1.5">
                      <button
                        onClick={() => setViewing(r)}
                        className="press inline-flex items-center gap-1 text-xs font-medium text-blue-400 hover:text-blue-300 hover:underline"
                      >
                        <Icon.File className="size-3.5" />
                        <span>Details →</span>
                      </button>
                      <button
                        onClick={() => setOutreachJob(r)}
                        className="press inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20"
                        title="Generate Alumni & Recruiter Outreach Notes"
                      >
                        🎓 Outreach
                      </button>
                      <button
                        onClick={() => setAtsAuditJob(r)}
                        className="press inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20"
                        title="Audit ATS Keyword Penetration"
                      >
                        📊 ATS Audit
                      </button>
                      <button
                        onClick={() => setInterviewPrepJob(r)}
                        className="press inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20 hover:bg-purple-500/20"
                        title="Generate 1-Page Interview Prep Cheat Sheet"
                      >
                        🧠 Prep
                      </button>
                    </div>
                  </div>

                  {/* Card Footer: Status & Action Controls */}
                  <div className="flex items-center justify-between gap-2 border-t border-line px-3.5 py-2.5 bg-surface-sunken/40">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => saveJob(r)}
                        aria-pressed={r.saved}
                        aria-label={r.saved ? 'Remove bookmark' : 'Save job'}
                        title={r.saved ? 'Saved' : 'Save'}
                        className={`press rounded p-1 transition-colors ${
                          r.saved ? 'text-blue-400 bg-blue-500/10' : 'text-n-500 hover:text-n-200'
                        }`}
                      >
                        <Icon.Bookmark filled={r.saved} className="size-3.5" />
                      </button>
                      <Status tone={meta.tone} title={r.status === 'skipped' ? r.fit_reason : ''}>
                        {meta.label}
                      </Status>
                    </div>

                    <div className="flex items-center gap-2">
                      {r.has_resume ? (
                        <a
                          href={api.agentResumeUrl(r.id, 'pdf')}
                          target="_blank"
                          rel="noreferrer"
                          className="press inline-flex items-center rounded border border-line bg-surface px-2.5 py-1 text-tiny font-medium text-blue-400 hover:border-n-600 hover:text-blue-300"
                          title={r.resume_version || ''}
                        >
                          PDF
                        </a>
                      ) : (
                        <button
                          disabled={busy}
                          onClick={() => onGenerate([r.id])}
                          className="press inline-flex items-center rounded border border-line bg-surface px-2.5 py-1 text-tiny font-medium text-blue-400 hover:border-n-600 disabled:opacity-40"
                        >
                          Tailor
                        </button>
                      )}

                      {r.resume_approved === 0 ? (
                        <button
                          onClick={() => setReviewing(r.id)}
                          className="press inline-flex items-center rounded border border-warn-500/30 bg-warn-950/20 px-2.5 py-1 text-tiny font-medium text-warn-400 hover:border-warn-500/50"
                        >
                          Review
                        </button>
                      ) : null}

                      {blocked ? null : (
                        <Button size="sm" variant="primary" disabled={busy} onClick={() => onApply([r.id])}>
                          Apply
                        </Button>
                      )}
                    </div>
                  </div>
                </m.article>
              )
            })}
          </div>
        </div>
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
              className: 'w-9 shrink-0',
            },
            { label: 'Role', className: 'min-w-[200px] w-[24%]' },
            { label: 'Company', className: 'min-w-[120px] w-[13%]' },
            { label: 'Location', className: 'min-w-[110px] w-[11%]' },
            { label: 'Category', className: 'min-w-[95px] w-[9%]' },
            { label: 'Score', className: 'min-w-[75px] w-[8%] whitespace-nowrap' },
            { label: 'Portal', className: 'min-w-[75px] w-[7%]' },
            { label: 'Status', className: 'min-w-[75px] w-[7%]' },
            { label: 'Found', className: 'min-w-[75px] w-[7%] whitespace-nowrap' },
            { label: 'Resume', className: 'min-w-[90px] w-[8%]' },
            { label: '', className: 'min-w-[80px] w-[6%] text-right' },
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

                <Td className="max-w-[11rem] truncate text-n-400" title={r.company_name || ''}>
                  {r.company_name || '—'}
                </Td>

                <Td className="max-w-[13rem] text-n-400" title={r.location || ''}>
                  <span className="block truncate">{r.location || (r.remote ? 'Remote' : '—')}</span>
                  {r.remote && r.location ? (
                    <span className="text-micro text-n-500">Remote</span>
                  ) : null}
                </Td>
                <Td>
                  <CategoryChip slug={r.role_category} />
                </Td>
                <Td className="whitespace-nowrap">
                  <FitScoreBadge
                    score={r.fit_score}
                    reason={r.fit_reason}
                    onClick={() => setAtsAuditJob(r)}
                  />
                </Td>
                <Td className="text-n-500">{r.source || '—'}</Td>

                <Td>
                  <Status tone={meta.tone} title={r.status === 'skipped' ? r.fit_reason : ''}>
                    {meta.label}
                  </Status>
                </Td>

                <Td className="whitespace-nowrap text-n-500">{when(r.discovered_at)}</Td>

                <Td className="whitespace-nowrap">
                  {r.has_resume ? (
                    <div className="flex items-center gap-2">
                      <a
                        href={api.agentResumeUrl(r.id, 'pdf')}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs font-medium text-blue-400 hover:underline"
                        title={r.resume_version || ''}
                      >
                        view
                      </a>
                      {r.resume_approved === 0 ? (
                        <button
                          onClick={() => setReviewing(r.id)}
                          className="press text-xs font-medium text-warn-400 hover:underline"
                        >
                          review
                        </button>
                      ) : null}
                    </div>
                  ) : (
                    <button
                      disabled={busy}
                      onClick={() => onGenerate([r.id])}
                      className="press text-xs font-medium text-blue-400 hover:underline disabled:opacity-40"
                    >
                      generate
                    </button>
                  )}
                </Td>

                <Td className="text-right whitespace-nowrap">
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      onClick={() => setViewing(r)}
                      className="press p-1 text-n-400 hover:text-blue-400 rounded hover:bg-surface"
                      title="View full details"
                    >
                      <Icon.File className="size-3.5" />
                    </button>
                    {blocked ? null : (
                      <Button size="sm" variant="ghost" disabled={busy} onClick={() => onApply([r.id])}>
                        Apply
                      </Button>
                    )}
                  </div>
                </Td>
              </Tr>
            )
          }}
        />
      )}

      {/* ------------------------------------------------------------ Intelligence & Detail Modals */}
      {viewing && (
        <JobDetail
          job={viewing}
          busy={busy}
          onClose={() => setViewing(null)}
          onApply={onApply}
          onGenerate={onGenerate}
          onReview={(id) => setReviewing(id)}
          onSave={saveJob}
          onPass={passJob}
          onOpenOutreach={(j) => setOutreachJob(j)}
          onOpenAtsAudit={(j) => setAtsAuditJob(j)}
          onOpenInterviewPrep={(j) => setInterviewPrepJob(j)}
        />
      )}

      {outreachJob && (
        <OutreachModal job={outreachJob} onClose={() => setOutreachJob(null)} />
      )}

      {atsAuditJob && (
        <AtsAuditModal job={atsAuditJob} onClose={() => setAtsAuditJob(null)} />
      )}

      {interviewPrepJob && (
        <InterviewPrepModal job={interviewPrepJob} onClose={() => setInterviewPrepJob(null)} />
      )}

      {reviewing && (
        <ResumeReview
          jobId={reviewing}
          onClose={() => setReviewing(null)}
          onApproved={() => {
            setReviewing(null)
            load()
          }}
        />
      )}
    </Section>
  )
}
