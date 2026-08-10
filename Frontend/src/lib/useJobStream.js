import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'

/**
 * Drives one background task: start it, stream its stdout over SSE, stop it.
 *
 * Takes the finish callback as a bare function. The old `{ onFinish }` shape
 * silently accepted a plain function too — destructuring just made `onFinish`
 * undefined, so the caller's refresh never ran and the screen sat stale after
 * every run.
 */
export function useJobStream(onFinish) {
  const [job, setJob] = useState(null)
  const [lines, setLines] = useState([])
  const [starting, setStarting] = useState('')
  const [error, setError] = useState('')
  const esRef = useRef(null)
  const finishRef = useRef(onFinish)
  finishRef.current = onFinish

  const detach = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
  }, [])

  const attach = useCallback(
    (jobId, cursor = 0) => {
      detach()
      const es = new EventSource(api.streamUrl(jobId, cursor))
      esRef.current = es
      es.onmessage = (evt) => {
        let msg
        try {
          msg = JSON.parse(evt.data)
        } catch {
          return
        }
        if (msg.type === 'lines') setLines((prev) => [...prev, ...msg.lines])
        if (msg.type === 'end') {
          setJob(msg.job)
          detach()
          finishRef.current?.(msg.job)
        }
      }
      es.onerror = () => detach()
    },
    [detach],
  )

  const start = useCallback(
    async (payload) => {
      setError('')
      setStarting(payload.key)
      try {
        const started = await api.run(payload)
        setJob(started)
        setLines([])
        attach(started.id, 0)
        return started
      } catch (e) {
        setError(e.message)
        return null
      } finally {
        setStarting('')
      }
    },
    [attach],
  )

  const stop = useCallback(async () => {
    if (!job) return
    try {
      await api.stop(job.id)
    } catch (e) {
      setError(e.message)
    }
  }, [job])

  const view = useCallback(
    (existing) => {
      setJob(existing)
      setLines([])
      attach(existing.id, 0)
    },
    [attach],
  )

  useEffect(() => detach, [detach])

  const busy = job?.status === 'running' || job?.status === 'stopping'
  return { job, lines, busy, starting, error, setError, start, stop, view, clear: () => setLines([]) }
}
