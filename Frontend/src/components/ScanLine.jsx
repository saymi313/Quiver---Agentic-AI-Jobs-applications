import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion as m } from 'motion/react'
import { prefersReducedMotion, springFor } from '../lib/motion'

/*
  The live scan line.

  Discovery is a long run, and a long run with no visible pulse reads as a hang.
  Tsenta answers this with a line that names what it is looking at right now —
  "scanning supabase.com/careers… 0 new" — so the wait feels like work rather
  than a spinner. This is that line: the newest meaningful log entry, carried on
  a spring as it changes, with a running count of what the scan has turned up.

  Feedback is continuous during the run and gone the moment it ends — a scan
  line still sitting there after the scan finished is worse than none, because
  it says the machine is doing something it is not.
*/

// The newest line worth surfacing: skip blank lines and the rule separators the
// runner prints between phases.
function latestOf(lines) {
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = (lines[i] || '').trim()
    if (line && !/^[-─—=]{2,}/.test(line)) return line.replace(/^\[[a-z]+\]\s*/i, '')
  }
  return ''
}

// A cumulative "found" count, read from any "N new" the run has logged.
function foundCount(lines) {
  let best = 0
  for (const line of lines) {
    const m2 = /(\d+)\s+(new|matched|found)/i.exec(line || '')
    if (m2) best = Math.max(best, Number(m2[1]))
  }
  return best
}

export default function ScanLine({ lines = [], active }) {
  const latest = useMemo(() => latestOf(lines), [lines])
  const found = useMemo(() => foundCount(lines), [lines])
  const reduced = prefersReducedMotion()

  // Hold the last line briefly after the run ends so the panel does not vanish
  // mid-sentence, then clear it.
  const [shown, setShown] = useState('')
  const timer = useRef(null)
  useEffect(() => {
    if (active) {
      setShown(latest)
      return
    }
    timer.current = setTimeout(() => setShown(''), 600)
    return () => clearTimeout(timer.current)
  }, [active, latest])

  const visible = active && !!shown

  return (
    <AnimatePresence initial={false}>
      {visible ? (
        <m.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={springFor()}
          className="material material-edge flex items-center gap-3 overflow-hidden rounded-md
            border border-line px-4 py-2.5"
        >
          {/* the pulse: proof of life, ~1Hz, and still for anyone who asked not
              to be moved */}
          <span className="relative flex size-2.5 shrink-0">
            {reduced ? null : (
              <m.span
                className="absolute inline-flex size-full rounded-full bg-blue-500"
                animate={{ scale: [1, 2.2], opacity: [0.6, 0] }}
                transition={{ duration: 1.2, repeat: Infinity, ease: 'easeOut' }}
              />
            )}
            <span className="relative inline-flex size-2.5 rounded-full bg-blue-500" />
          </span>

          {/* the line itself, springing as it changes so the eye follows the
              text rather than watching it flip */}
          <div className="min-w-0 flex-1 overflow-hidden">
            <AnimatePresence mode="popLayout" initial={false}>
              <m.p
                key={shown}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={springFor()}
                className="truncate font-mono text-tiny text-n-300"
              >
                {shown}
              </m.p>
            </AnimatePresence>
          </div>

          {found ? (
            <span className="shrink-0 rounded-full bg-ok-tint px-2 py-0.5 text-micro font-medium
              tabular-nums text-ok-400">
              {found} new
            </span>
          ) : null}
        </m.div>
      ) : null}
    </AnimatePresence>
  )
}
