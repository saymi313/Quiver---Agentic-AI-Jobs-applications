import { useAgentRun } from '../lib/useAgentRun'
import Console from '../components/Console'
import TrackedJobs from '../components/TrackedJobs'
import AddJobByUrl from '../components/AddJobByUrl'
import { Empty, Note, PageHead, Status, Switch } from '../components/ui'

/*
  Jobs — the table, and what it takes to act on it.

  Everything that is not the table has moved off this screen: the figures to
  the dashboard, the search and portal configuration to settings. What is left
  is a list you can narrow and a set of rows you can act on, which is what the
  screen is for.

  Nothing here submits on its own. An application happens only when a button in
  this table is pressed.
*/

export default function JobsTab() {
  const run = useAgentRun()
  const {
    overview, stream, busy, refreshKey, refresh,
    applyToJobs, generateResumes, runSettings, setRunSetting,
  } = run

  if (!overview) return <Empty title="Loading" />

  const { dryRun, headed, workers } = runSettings

  return (
    <div className="space-y-4">
      <PageHead
        title="Jobs"
        description="Every role the agent found, with a resume tailored to each. Narrow the list, then apply to what you pick."
      />

      {stream.error ? (
        <Note tone="bad" title="Could not start that" onDismiss={() => stream.setError('')}>
          {stream.error}
        </Note>
      ) : null}

      <AddJobByUrl onAdded={refresh} />

      <TrackedJobs
        refreshKey={refreshKey}
        busy={busy}
        onApply={applyToJobs}
        onGenerate={generateResumes}
        toolbar={
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <Switch
              checked={dryRun}
              onChange={(v) => setRunSetting({ dryRun: v })}
              label="Dry run"
            />
            <Switch
              checked={headed}
              onChange={(v) => setRunSetting({ headed: v })}
              label="Watch the browser"
            />
            {!headed ? (
              <label className="flex items-center gap-2 text-sm text-n-400">
                <span>At once</span>
                <select
                  value={workers}
                  onChange={(e) => setRunSetting({ workers: Number(e.target.value) })}
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
    </div>
  )
}
