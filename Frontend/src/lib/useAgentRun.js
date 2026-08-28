import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { useJobStream } from './useJobStream'

/*
  Everything a screen needs to run the agent and react to what it did.

  Two screens now start runs — the dashboard finds roles, the jobs table
  applies to them — and both need the same four things: the overview, a stream
  to watch, a key that tells child panels to refetch, and the apply settings
  that govern what a run actually does. Holding that in one hook keeps the two
  screens from drifting apart on the details that matter, like whether a run is
  a dry run.

  The apply settings live here rather than in component state because the
  answer must be the same wherever the button is pressed. `dryRun` in
  particular: two screens each remembering their own idea of it is how someone
  ends up submitting a real application from the one that had it off.
*/

/** Read once at module load so both screens start from the same values, and a
 *  screen mounted later does not reset what the other one chose. */
const shared = {
  dryRun: true,
  // Headless by default so background runs never pop up desktop windows
  headed: false,
  workers: 1,
}

export function useAgentRun() {
  const [overview, setOverview] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [settings, setSettings] = useState(shared)

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

  const setRunSetting = useCallback((patch) => {
    Object.assign(shared, patch)
    setSettings({ ...shared })
  }, [])

  const busy = stream.busy || !!stream.starting

  const applyToJobs = useCallback(
    (ids) =>
      ids.length &&
      stream.start({
        key: 'agent_apply',
        job_ids: ids,
        dry_run: settings.dryRun,
        headed: settings.headed,
        workers: settings.headed ? 1 : settings.workers,
      }),
    [stream, settings],
  )

  const generateResumes = useCallback(
    (ids) => ids.length && stream.start({ key: 'agent_resumes', job_ids: ids }),
    [stream],
  )

  // Approve a form that was held for review, and submit it. Same apply path,
  // with the review pause forced off for this one job.
  const approveAndSubmit = useCallback(
    (jobId) =>
      stream.start({
        key: 'agent_apply',
        job_ids: [jobId],
        dry_run: false,
        headed: settings.headed,
        workers: 1,
        no_review: true,
      }),
    [stream, settings],
  )

  /** Start a discovery run from whatever the saved search settings say. The
   *  button that does this is not on the same screen as those settings any
   *  more, so it reads them rather than owning them. */
  const findJobs = useCallback(() => {
    const s = overview?.settings?.search || {}
    return stream.start({
      key: 'agent_discover',
      sources: s.sources?.length ? s.sources : ['yc', 'hn', 'remote', 'hidden'],
      limit: Number(s.depth) || 25,
      no_people: s.find_people === false,
      no_ats: s.scan_ats === false,
    })
  }, [stream, overview])

  return {
    overview,
    refresh,
    refreshKey,
    stream,
    busy,
    applyToJobs,
    generateResumes,
    approveAndSubmit,
    findJobs,
    runSettings: settings,
    setRunSetting,
  }
}
