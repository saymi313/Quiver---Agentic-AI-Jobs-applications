import { Button, Metric } from './ui'
import { GlassPanel } from './apple'

/**
 * Where the pipeline stands, as one row of figures.
 *
 * Deliberately the four numbers that describe a state you can act on —
 * fetched, ready, applied, failed — rather than every count the database can
 * produce. Contact and company totals belong on Outreach, where they are
 * actionable.
 */
export default function Pipeline({ stats, retentionDays, schedule, queue, busy, onRetry }) {
  const byStatus = stats.jobsByStatus || {}
  const ready = stats.matchedJobs || 0
  const applied = byStatus.applied || 0
  const failed = byStatus.failed || 0
  const retrying = (queue?.pending || 0) + (queue?.failed || 0)

  return (
    <GlassPanel>
      <div className="p-4">
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
      </div>
    </GlassPanel>
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
