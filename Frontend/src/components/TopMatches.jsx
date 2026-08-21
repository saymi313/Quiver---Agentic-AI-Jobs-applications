import { useEffect, useMemo, useState } from 'react'
import { motion as m } from 'motion/react'
import { api } from '../lib/api'
import { springFor } from '../lib/motion'
import { Button, Icon } from './ui'
import { CategoryChip, ScoreRing } from './apple'

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

export default function TopMatches({ refreshKey, busy, onApply }) {
  const [rows, setRows] = useState(null)

  useEffect(() => {
    let alive = true
    api
      .agentJobs({ status: 'not_applied', limit: 60 })
      .then((d) => alive && setRows(d.rows || []))
      .catch(() => alive && setRows([]))
    return () => {
      alive = false
    }
  }, [refreshKey])

  const best = useMemo(
    () =>
      (rows || [])
        .filter((r) => (r.fit_score || 0) > 0)
        .sort((a, b) => (b.fit_score || 0) - (a.fit_score || 0))
        .slice(0, SHOWN),
    [rows],
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

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {best.map((r, i) => (
          <m.article
            key={r.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...springFor(), delay: i * 0.04 }}
            className="flex flex-col overflow-hidden rounded-md border border-line bg-surface"
          >
            <div className={`flex items-start gap-3 p-4 ${TINTS[i % TINTS.length]}`}>
              <div className="min-w-0 flex-1">
                <p className="truncate text-micro text-n-400" title={r.company_name || ''}>
                  {r.company_name || 'Unknown company'}
                </p>
                <h3 className="mt-0.5 line-clamp-2 text-sm font-semibold text-n-100">
                  {r.title}
                </h3>
                {r.location ? (
                  <p className="mt-1 truncate text-micro text-n-400">{r.location}</p>
                ) : null}
                <CategoryChip slug={r.role_category} className="mt-2" />
              </div>
              <ScoreRing value={r.fit_score} />
            </div>

            <div className="flex items-center justify-between gap-2 border-t border-line px-3 py-2">
              <a
                href={r.url}
                target="_blank"
                rel="noreferrer"
                className="press inline-flex min-w-0 items-center gap-1.5 text-micro text-n-400
                  hover:text-n-100"
              >
                <Icon.Doc className="size-3.5 shrink-0" />
                <span className="truncate">{r.source || 'posting'}</span>
              </a>
              <Button
                size="sm"
                variant="primary"
                disabled={busy}
                onClick={() => onApply([r.id])}
              >
                Apply
              </Button>
            </div>
          </m.article>
        ))}
      </div>
    </section>
  )
}
