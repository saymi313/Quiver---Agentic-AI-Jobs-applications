import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { useJobStream } from '../lib/useJobStream'
import Console from '../components/Console'
import TrackedJobs from '../components/TrackedJobs'
import Settings from '../components/Settings'
import Portals from '../components/Portals'
import Proposals from '../components/Proposals'
import TopMatches from '../components/TopMatches'
import {
  Button,
  Checkbox,
  Disclosure,
  Empty,
  Field,
  Input,
  Metric,
  Note,
  PageHead,
  Section,
  Status,
  Switch,
} from '../components/ui'

/*
  Jobs — find roles, review them, apply.

  The screen opens on the thing you came for: the tracked jobs table. Search
  configuration and profile settings sit collapsed above it, and the run log
  sits below. The previous version led with six stat tiles and three equally
  weighted mode cards, which buried the table that does the actual work.
*/

const SOURCES = [
  { key: 'yc', label: 'Y Combinator' },
  { key: 'hn', label: 'HN "Who is hiring"' },
  { key: 'remote', label: 'Remote & EU boards' },
  { key: 'hidden', label: 'Hidden job market' },
]

export default function JobsTab() {
  const [overview, setOverview] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [openPanel, setOpenPanel] = useState('')

  const refresh = useCallback(async () => {
    const data = await api.agentOverview()
    setOverview(data)
    setRefreshKey((k) => k + 1)
    return data
  }, [])

  const stream = useJobStream(refresh)

  useEffect(() => {
    refresh().then((o) => {
      if (o?.activeJob) stream.view(o.activeJob)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh])

  const [sources, setSources] = useState(['yc', 'hn', 'remote', 'hidden'])
  const [depth, setDepth] = useState(25)
  const [findPeople, setFindPeople] = useState(true)
  const [scanAts, setScanAts] = useState(true)

  // Apply behaviour. These live beside the table because that is where the
  // Apply button is — a setting three panels away from the action it governs
  // is a setting nobody reads.
  const [dryRun, setDryRun] = useState(true)
  // Headed by default: Ashby's anti-bot scoring rejected a headless browser
  // as spam in testing and accepted the identical submission with a visible one.
  const [headed, setHeaded] = useState(true)
  // Only offered with the browser hidden: several visible Chromium windows
  // fighting for focus is unusable, and focus theft corrupts the fields being
  // typed into.
  const [workers, setWorkers] = useState(1)

  const busy = stream.busy || !!stream.starting

  const applyToJobs = useCallback(
    (ids) =>
      ids.length &&
      stream.start({
        key: 'agent_apply',
        job_ids: ids,
        dry_run: dryRun,
        headed,
        workers: headed ? 1 : workers,
      }),
    [stream, dryRun, headed, workers],
  )
  const generateResumes = useCallback(
    (ids) => ids.length && stream.start({ key: 'agent_resumes', job_ids: ids }),
    [stream],
  )

  if (!overview) return <Empty title="Loading" />

  const targeting = overview.settings.targeting || {}

  return (
    <div className="space-y-4">
      <PageHead
        title="Jobs"
        description="Roles the agent found across your ten categories, with a resume tailored to each. Nothing is applied to until you say so."
        actions={
          <Button
            variant="primary"
            disabled={busy || !sources.length}
            busy={stream.starting === 'agent_discover'}
            onClick={() =>
              stream.start({
                key: 'agent_discover',
                sources,
                limit: Number(depth),
                no_people: !findPeople,
                no_ats: !scanAts,
              })
            }
          >
            Find new jobs
          </Button>
        }
      />

      <AddJobByUrl onAdded={refresh} />

      {stream.error ? (
        <Note tone="bad" title="Could not start that" onDismiss={() => stream.setError('')}>
          {stream.error}
        </Note>
      ) : null}

      {!overview.llm.available ? (
        <Note tone="warn" title="No AI provider configured">
          {overview.llm.reason} Finding and scoring roles still works; tailored resumes and form
          answers do not.
        </Note>
      ) : null}

      {overview.store?.fallback ? (
        <Note tone="warn" title="MongoDB unreachable, using local SQLite">
          {overview.store.reason} Everything still works and this run's data stays on disk.
        </Note>
      ) : null}

      <Proposals busy={busy} onApply={applyToJobs} refreshKey={refreshKey} />

      <TopMatches refreshKey={refreshKey} busy={busy} onApply={applyToJobs} />

      <Pipeline
        stats={overview.stats}
        retentionDays={overview.settings.limits?.retention_days ?? 3}
        schedule={overview.schedule}
        queue={overview.queue}
        busy={busy}
        onRetry={() => stream.start({ key: 'agent_tasks' })}
      />

      <Disclosure
        title="Search"
        description={`${sources.length} source${sources.length === 1 ? '' : 's'} · depth ${depth} · roles posted in the last ${targeting.max_age_days ?? 3} days, asking ${targeting.min_years_experience ?? 1} to ${targeting.max_years_experience ?? 3} years`}
        open={openPanel === 'search'}
        onToggle={(v) => setOpenPanel(v ? 'search' : '')}
      >
        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2.5">
            <p className="text-micro font-medium tracking-wide text-n-400 uppercase">Sources</p>
            {SOURCES.map((s) => (
              <Checkbox
                key={s.key}
                checked={sources.includes(s.key)}
                onChange={(on) =>
                  setSources((prev) => (on ? [...prev, s.key] : prev.filter((k) => k !== s.key)))
                }
                label={s.label}
              />
            ))}
          </div>
          <div className="space-y-3">
            <Field label="Depth" hint="Companies per source, and roles scored.">
              <Input
                type="number"
                min={1}
                max={200}
                value={depth}
                onChange={(e) => setDepth(e.target.value)}
              />
            </Field>
            <Checkbox
              checked={scanAts}
              onChange={setScanAts}
              label="Scan career portals"
              hint="Detect Greenhouse, Lever and Ashby boards, then pull their live openings."
            />
            <Checkbox
              checked={findPeople}
              onChange={setFindPeople}
              label="Find and verify emails"
              hint="Crawl team pages, then MX and SMTP check every address."
            />
          </div>
        </div>
      </Disclosure>

      <Portals
        open={openPanel === 'portals'}
        onToggle={(v) => setOpenPanel(v ? 'portals' : '')}
      />

      <Settings
        overview={overview}
        onSaved={refresh}
        open={openPanel === 'settings'}
        onToggle={(v) => setOpenPanel(v ? 'settings' : '')}
      />

      <TrackedJobs
        refreshKey={refreshKey}
        busy={busy}
        onApply={applyToJobs}
        onGenerate={generateResumes}
        toolbar={
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <Switch checked={dryRun} onChange={setDryRun} label="Dry run" />
            <Switch checked={headed} onChange={setHeaded} label="Watch the browser" />
            {!headed ? (
              <label className="flex items-center gap-2 text-sm text-n-400">
                <span>At once</span>
                <select
                  value={workers}
                  onChange={(e) => setWorkers(Number(e.target.value))}
                  aria-label="How many applications to run at once"
                  className="h-7 rounded-sm border border-line-strong bg-surface px-2 text-sm text-n-100"
                >
                  <option value={1}>1</option>
                  <option value={2}>2</option>
                  <option value={3}>3</option>
                </select>
              </label>
            ) : null}
            {!dryRun ? <Status tone="bad">applications will be submitted</Status> : null}
          </div>
        }
      />

      <Console
        lines={stream.lines}
        job={stream.job}
        onStop={stream.stop}
        onClear={stream.clear}
      />

      <ApplicationLog refreshKey={refreshKey} />
    </div>
  )
}

/* ---------------------------------------------------------------- summary */

/**
 * Where the pipeline stands, as one row of figures.
 *
 * Deliberately the four numbers that describe a state you can act on —
 * fetched, ready, applied, failed — rather than every count the database can
 * produce. Contact and company totals belong on Outreach, where they are
 * actionable.
 */
function Pipeline({ stats, retentionDays, schedule, queue, busy, onRetry }) {
  const byStatus = stats.jobsByStatus || {}
  const ready = stats.matchedJobs || 0
  const applied = byStatus.applied || 0
  const failed = byStatus.failed || 0
  const retrying = (queue?.pending || 0) + (queue?.failed || 0)

  return (
    <Section>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
        <Metric
          label="Fetched"
          value={stats.jobs}
          hint={`kept for ${retentionDays} day${retentionDays === 1 ? '' : 's'}`}
        />
        <Metric label="Ready to apply" value={ready} hint="passed every gate" />
        <Metric
          label="Applied"
          value={applied}
          hint={`${stats.applications || 0} attempt${stats.applications === 1 ? '' : 's'}`}
        />
        <Metric label="Failed" value={failed} hint={failed ? 'see the reason on the row' : 'none'} />
      </dl>
      {schedule?.enabled ? (
        <p className="mt-3 border-t border-line pt-2.5 text-tiny leading-relaxed text-n-500">
          Scheduled: next search {nextWhen(schedule.nextDiscoverAt)}
          {retrying
            ? `; ${retrying} failed step${retrying === 1 ? '' : 's'} queued to retry ${nextWhen(schedule.nextTasksAt)}`
            : ''}
          . Searches run on their own — applying still takes your click.
        </p>
      ) : retrying ? (
        <div className="mt-3 flex items-center justify-between gap-4 border-t border-line pt-2.5">
          <p className="text-tiny leading-relaxed text-n-500">
            {retrying} step{retrying === 1 ? '' : 's'} from the last search failed and can be
            retried — descriptions that would not load, resume builds that errored.
          </p>
          <Button disabled={busy} onClick={onRetry}>
            Retry failed steps
          </Button>
        </div>
      ) : null}
    </Section>
  )
}

function nextWhen(iso) {
  if (!iso) return 'soon'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime()) || d.getTime() <= Date.now()) return 'within a minute'
  const mins = Math.round((d.getTime() - Date.now()) / 60000)
  if (mins < 60) return `in ${mins} min`
  return `at ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
}

/* ------------------------------------------------------- application log */

const APP_TONE = { submitted: 'ok', filled: 'info', failed: 'bad', skipped: 'warn' }

function ApplicationLog({ refreshKey }) {
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

/*
  Paste a link, track the job.

  Discovery finds roles the agent went looking for; this is for the one a
  friend sent you. Same pipeline from the URL onwards — fetch the description,
  classify the role, score it against the profile — so the row that appears is
  indistinguishable from a discovered one.
*/
function AddJobByUrl({ onAdded }) {
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
      description="Paste any posting URL. Quiver reads it, works out the role and scores it like any other."
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
