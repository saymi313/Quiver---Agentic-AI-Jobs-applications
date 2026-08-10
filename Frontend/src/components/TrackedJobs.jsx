import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { Button, Empty, Icon, Input, Section, Select, Status, Table, Tag, Td, Tr } from './ui'

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
  const [filters, setFilters] = useState({ status: 'not_applied', category: '', source: '', q: '' })
  const [search, setSearch] = useState('')

  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => ({ ...f, q: search })), 300)
    return () => clearTimeout(t)
  }, [search])

  const load = useCallback(() => {
    let alive = true
    setLoading(true)
    api
      .agentJobs({ ...filters, limit: 400 })
      .then((d) => alive && setData(d))
      .catch(() => alive && setData({ rows: [], categories: [], sources: {}, total: 0 }))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [filters])

  useEffect(() => load(), [load, refreshKey])

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
        data ? `${rows.length} of ${data.total} tracked` : 'Everything the agent has found.'
      }
      flush
      actions={
        <Button size="sm" variant="ghost" onClick={load}>
          <Icon.Refresh />
          Refresh
        </Button>
      }
    >
      {/* --------------------------------------------------------- controls */}
      {/* Widths live on wrappers, not on the controls. The kit's inputs are
          w-full by design, and overriding that from a className is a
          specificity coin-toss that Tailwind lost here at least once. */}
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <div className="w-40">
          <Select
            value={filters.status}
            onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
            aria-label="Filter by application status"
          >
            {STATUS_FILTERS.map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </Select>
        </div>

        <div className="w-44">
          <Select
            value={filters.category}
            onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value }))}
            aria-label="Filter by role category"
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.label} ({c.count})
              </option>
            ))}
          </Select>
        </div>

        <div className="w-36">
          <Select
            value={filters.source}
            onChange={(e) => setFilters((f) => ({ ...f, source: e.target.value }))}
            aria-label="Filter by portal source"
          >
            <option value="">All portals</option>
            {sources.map(([name, count]) => (
              <option key={name} value={name}>
                {name} ({count})
              </option>
            ))}
          </Select>
        </div>

        <div className="min-w-[10rem] flex-1">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search"
            aria-label="Search tracked jobs"
            className="h-8 py-0"
          />
        </div>
      </div>

      {toolbar ? <div className="border-b border-line px-4 py-2.5">{toolbar}</div> : null}

      {/* Selection bar replaces the toolbar row rather than stacking under it. */}
      {chosen.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3 border-b border-line bg-raised px-4 py-2.5">
          <span className="text-tiny text-n-300">{chosen.length} selected</span>
          <Button size="sm" variant="primary" disabled={busy} onClick={() => onApply(ids)}>
            Apply
          </Button>
          <Button size="sm" disabled={busy} onClick={() => onGenerate(ids)}>
            Generate resumes
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
            Clear
          </Button>
        </div>
      ) : null}

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
                  className="size-3.5 accent-brand-500"
                />
              ),
              className: 'w-8',
            },
            { label: 'Role' },
            { label: 'Company' },
            { label: 'Category' },
            { label: 'Portal' },
            { label: 'Status' },
            { label: 'Found' },
            { label: 'Resume' },
            { label: '', className: 'w-16' },
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
                    className="size-3.5 accent-brand-500 disabled:opacity-25"
                  />
                </Td>

                <Td className="max-w-[22rem]">
                  <a
                    href={r.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm text-n-200 hover:text-brand-400"
                  >
                    {r.title}
                  </a>
                  {r.fit_score ? (
                    <span className="ml-1.5 text-micro text-n-600">{Math.round(r.fit_score)}</span>
                  ) : null}
                  {r.failure_reason ? (
                    <p className="mt-0.5 text-micro leading-snug text-bad-400/80">
                      {r.failure_reason}
                    </p>
                  ) : null}
                </Td>

                {/* Some boards put a whole paragraph in the company field. */}
                <Td className="max-w-[11rem] truncate text-n-400" title={r.company_name || ''}>
                  {r.company_name || '—'}
                </Td>
                <Td>
                  {r.role_category ? (
                    <Tag className="whitespace-nowrap">{r.role_category.replace(/_/g, ' ')}</Tag>
                  ) : null}
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
                    <a
                      href={api.agentResumeUrl(r.id, 'pdf')}
                      target="_blank"
                      rel="noreferrer"
                      className="text-brand-400 hover:underline"
                      title={r.resume_version || ''}
                    >
                      view
                    </a>
                  ) : (
                    <button
                      disabled={busy}
                      onClick={() => onGenerate([r.id])}
                      className="text-n-500 transition-colors hover:text-n-200 disabled:opacity-40"
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
