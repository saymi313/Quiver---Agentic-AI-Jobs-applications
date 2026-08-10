import { useEffect, useRef, useState } from 'react'
import { Button, Section, Status } from './ui'

/*
  The run log. Collapsed to a single line when nothing has run, because an
  empty 24rem black box was the largest element on two of the three screens.
*/

const JOB_TONE = {
  running: 'accent',
  finished: 'ok',
  failed: 'bad',
  stopped: 'warn',
  stopping: 'warn',
}

/** Colour carries severity; the prefix already carries the category, so only
 *  lines that need attention get a colour at all. */
export function lineTone(line) {
  if (/^\[done\]|SUBMITTED|^\s*\[(SENT|OK|DONE)/i.test(line)) return 'text-ok-400'
  if (/^\s*\[(FAIL|ERROR)/i.test(line) || /exited with code|Traceback|FAILED|REJECTED/.test(line))
    return 'text-bad-400'
  if (/^\s*\[(SKIP|WARN)/i.test(line) || /^\[stopped|SKIPPED|\brisky\b/.test(line))
    return 'text-warn-400'
  if (/^---\s/.test(line)) return 'text-n-200'
  if (/^\$ /.test(line)) return 'text-brand-400'
  return 'text-n-400'
}

export default function Console({ lines, job, onStop, onClear, height = 'h-72' }) {
  const boxRef = useRef(null)
  const [stick, setStick] = useState(true)

  useEffect(() => {
    if (stick && boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight
  }, [lines, stick])

  const running = job?.status === 'running' || job?.status === 'stopping'

  return (
    <Section
      title="Run log"
      description={job ? job.label : 'Nothing has run yet. Output from the agent appears here.'}
      flush={lines.length > 0}
      actions={
        <div className="flex items-center gap-3">
          {job ? (
            <Status tone={JOB_TONE[job.status] || 'neutral'} pulse={running}>
              {job.status}
              {job.returncode != null && !running ? ` (${job.returncode})` : ''}
            </Status>
          ) : null}
          {running ? (
            <Button size="sm" variant="danger" onClick={onStop}>
              Stop
            </Button>
          ) : lines.length ? (
            <Button size="sm" variant="ghost" onClick={onClear}>
              Clear
            </Button>
          ) : null}
        </div>
      }
    >
      {lines.length === 0 ? null : (
        <>
          <div
            ref={boxRef}
            onScroll={(e) => {
              const el = e.currentTarget
              setStick(el.scrollHeight - el.scrollTop - el.clientHeight < 40)
            }}
            className={`${height} overflow-auto bg-sunken px-4 py-3 font-mono text-micro leading-[1.7]`}
          >
            {lines.map((line, i) => (
              <div key={i} className={`whitespace-pre-wrap ${lineTone(line)}`}>
                {line || ' '}
              </div>
            ))}
          </div>
          {!stick && running ? (
            <button
              onClick={() => setStick(true)}
              className="w-full border-t border-line py-1.5 text-tiny text-n-400 hover:text-n-200"
            >
              Jump to latest
            </button>
          ) : null}
        </>
      )}
    </Section>
  )
}
