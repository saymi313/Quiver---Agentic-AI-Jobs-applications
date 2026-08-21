import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion as m } from 'motion/react'
import { api } from '../lib/api'
import { springFor } from '../lib/motion'
import { Button, Icon } from './ui'
import { CategoryChip, ScoreRing } from './apple'
import JobDetail from './JobDetail'

const CUR = { USD: '$', GBP: '£', EUR: '€', JPY: '¥', INR: '₹' }

/** A one-line salary for a card: "$120k–150k". */
function salaryHint(job) {
  const { salary_min: lo, salary_max: hi, salary_currency: cur } = job
  const sym = CUR[cur] || (cur ? `${cur} ` : '')
  const k = (n) => `${Math.round(n / 1000)}k`
  if (lo != null && hi != null) return `${sym}${k(lo)}–${k(hi)}`
  return `${sym}${k(lo ?? hi)}`
}

/*
  The best few roles, as cards.

  The table below holds everything and answers "what is there". This row
  answers a different question — "what should I look at first" — and a card
  answers it better than a row, because the score can be a shape rather than a
  number in a column.

  The tints rotate by position and mean nothing. They separate one card from
  the next, which is all a tint should ever do; the score ring carries the
  actual signal.
*/

const TINTS = ['bg-tint-1', 'bg-tint-2', 'bg-tint-3', 'bg-tint-4']
const SHOWN = 4

export default function TopMatches({ refreshKey, busy, onApply, onGenerate }) {
  const [rows, setRows] = useState(null)
  // Passing a card hides it at once — waiting for a refetch to drop it is the
  // kind of lag the design language treats as a regression.
  const [hidden, setHidden] = useState(() => new Set())
  const [savedIds, setSavedIds] = useState(() => new Set())
  const [viewing, setViewing] = useState(null)

  useEffect(() => {
    let alive = true
    api
      .agentJobs({ status: 'not_applied', limit: 60 })
      .then((d) => {
        if (!alive) return
        setRows(d.rows || [])
        setSavedIds(new Set((d.rows || []).filter((r) => r.saved).map((r) => r.id)))
      })
      .catch(() => alive && setRows([]))
    return () => {
      alive = false
    }
  }, [refreshKey])

  const pass = (job) => {
    setHidden((prev) => new Set(prev).add(job.id))
    api.agentPassJob(job.id).catch(() => {})
  }
  const save = (job) => {
    const next = !savedIds.has(job.id)
    setSavedIds((prev) => {
      const s = new Set(prev)
      next ? s.add(job.id) : s.delete(job.id)
      return s
    })
    api.agentSaveJob(job.id, next).catch(() => {})
  }

  const best = useMemo(
    () =>
      (rows || [])
        .filter((r) => (r.fit_score || 0) > 0 && !hidden.has(r.id))
        .sort((a, b) => (b.fit_score || 0) - (a.fit_score || 0))
        .slice(0, SHOWN),
    [rows, hidden],
  )

  // Nothing scored yet is not news, and an empty row of cards is worse than
  // no row at all.
  if (!best.length) return null

  return (
    <section>
      <div className="flex items-baseline justify-between pb-3">
        <h2 className="text-sm font-semibold text-n-100">Top matches</h2>
        <span className="text-tiny text-n-400">
          Best {best.length} of {rows.length} ready to apply
        </span>
      </div>

      {/* popLayout so a passed card's neighbours slide up to fill the gap
          rather than the row snapping — the motion says "this one is gone". */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <AnimatePresence mode="popLayout" initial={false}>
          {best.map((r, i) => {
            const saved = savedIds.has(r.id)
            return (
              <m.article
                key={r.id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.94 }}
                transition={{ ...springFor(), delay: i * 0.04 }}
                className="flex flex-col overflow-hidden rounded-md border border-line bg-surface"
              >
                <button
                  onClick={() => setViewing({ ...r, saved })}
                  className={`press flex items-start gap-3 p-4 text-left ${TINTS[i % TINTS.length]}`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-micro text-n-400" title={r.company_name || ''}>
                      {r.company_name || 'Unknown company'}
                    </p>
                    <h3 className="mt-0.5 line-clamp-2 text-sm font-semibold text-n-100">
                      {r.title}
                    </h3>
                    {r.salary_min ? (
                      <p className="mt-1 truncate text-micro font-medium text-n-300">
                        {salaryHint(r)}
                      </p>
                    ) : r.location ? (
                      <p className="mt-1 truncate text-micro text-n-400">{r.location}</p>
                    ) : null}
                    <CategoryChip slug={r.role_category} className="mt-2" />
                  </div>
                  <ScoreRing value={r.fit_score} />
                </button>

                <div className="flex items-center gap-1.5 border-t border-line px-2.5 py-2">
                  <button
                    onClick={() => save(r)}
                    aria-pressed={saved}
                    aria-label={saved ? 'Saved' : 'Save'}
                    className={`press rounded p-1 ${
                      saved ? 'text-blue-500' : 'text-n-400 hover:text-n-200'
                    }`}
                  >
                    <Icon.Bookmark filled={saved} className="size-3.5" />
                  </button>
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => pass(r)}>
                    Pass
                  </Button>
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={busy}
                    className="ml-auto"
                    onClick={() => onApply([r.id])}
                  >
                    Apply
                  </Button>
                </div>
              </m.article>
            )
          })}
        </AnimatePresence>
      </div>

      <JobDetail
        job={viewing}
        busy={busy}
        onClose={() => setViewing(null)}
        onApply={(ids) => {
          setViewing(null)
          onApply(ids)
        }}
        onGenerate={onGenerate}
        onSave={(job) => {
          save(job)
          setViewing((v) => (v ? { ...v, saved: !v.saved } : v))
        }}
        onPass={(job) => {
          setViewing(null)
          pass(job)
        }}
      />
    </section>
  )
}
