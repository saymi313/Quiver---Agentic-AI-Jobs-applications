import { useAgentRun } from '../lib/useAgentRun'
import Console from '../components/Console'
import ScanLine from '../components/ScanLine'
import Pipeline from '../components/Pipeline'
import Proposals from '../components/Proposals'
import TopMatches from '../components/TopMatches'
import ApplicationLog from '../components/ApplicationLog'
import { Button, Empty, Note, PageHead } from '../components/ui'

/*
  The dashboard: where things stand, and the one button that moves them.

  It answers three questions in the order they are asked — is there anything
  waiting on me, what is worth looking at first, and how is the pipeline doing
  overall — and then gets out of the way. The jobs table lives one click
  further in, because a table is something you go to, not something you should
  have to scroll past.

  Nothing here is a duplicate of the Jobs screen: the review queue and the top
  matches are decisions, and the table is a list. They belong on different
  screens for the same reason a mail app puts unread counts in one place and
  the messages in another.
*/

export default function DashboardTab({ onOpenJobs }) {
  const run = useAgentRun()
  const { overview, stream, busy, refreshKey, applyToJobs, findJobs } = run

  if (!overview) return <Empty title="Loading" />

  const search = overview.settings.search || {}
  const sourceCount = search.sources?.length ?? 4

  return (
    <div className="space-y-4">
      <PageHead
        title="Dashboard"
        description="What the agent has found, what is waiting on you, and how the pipeline is moving."
        actions={
          <Button
            variant="primary"
            disabled={busy || !sourceCount}
            busy={stream.starting === 'agent_discover'}
            onClick={findJobs}
          >
            Find new jobs
          </Button>
        }
      />

      {stream.error ? (
        <Note tone="bad" title="Could not start that" onDismiss={() => stream.setError('')}>
          {stream.error}
        </Note>
      ) : null}

      <ScanLine lines={stream.lines} active={busy} />

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

      <TopMatches
        refreshKey={refreshKey}
        busy={busy}
        onApply={applyToJobs}
        onGenerate={run.generateResumes}
      />

      <Pipeline
        stats={overview.stats}
        retentionDays={overview.settings.limits?.retention_days ?? 3}
        schedule={overview.schedule}
        queue={overview.queue}
        busy={busy}
        onRetry={() => stream.start({ key: 'agent_tasks' })}
      />

      <Console
        lines={stream.lines}
        job={stream.job}
        onStop={stream.stop}
        onClear={stream.clear}
      />

      <ApplicationLog refreshKey={refreshKey} onApprove={run.approveAndSubmit} />

      <p className="pt-1 text-tiny text-n-500">
        {overview.stats.jobs} roles tracked across {sourceCount} source
        {sourceCount === 1 ? '' : 's'}.{' '}
        <button onClick={onOpenJobs} className="press text-blue-500 hover:underline">
          Open the jobs table
        </button>{' '}
        to filter them and apply.
      </p>
    </div>
  )
}
