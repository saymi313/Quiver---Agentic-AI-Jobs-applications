import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion as m } from 'motion/react'
import { api } from '../lib/api'
import { springFor } from '../lib/motion'
import { Button, Empty, Note, Section, Status, Table, Tag, Td, Tr } from './ui'

/*
  Auto Apply's review queue.

  The agent shortlists; you decide. Approving records the decision and hands
  the ids to the ordinary Apply path — the same one a manual selection uses —
  so there is exactly one route to an employer and it always runs past a human.

  The panel hides itself when the queue is empty, because an empty queue is not
  news. It appears when there is a decision to make.
*/

export default function Proposals({ busy, onApply, refreshKey }) {
  const [data, setData] = useState(null)
  const [chosen, setChosen] = useState(() => new Set())
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api
      .agentProposals()
      .then((d) => {
        setData(d)
        setChosen(new Set((d.rows || []).map((r) => r.id)))
      })
      .catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    load()
  }, [load, refreshKey])

  const rows = data?.rows || []
  const ids = useMemo(() => rows.filter((r) => chosen.has(r.id)).map((r) => r.id), [rows, chosen])

  const decide = useCallback(
    async (decision) => {
      if (!ids.length) return
      setWorking(true)
      setError('')
      try {
        await api.agentDecideProposals(ids, decision)
        // Approving records the decision; sending is still the ordinary apply
        // path, started here with exactly the ids that were approved.
        if (decision === 'approved') onApply?.(ids)
        load()
      } catch (e) {
        setError(e.message)
      } finally {
        setWorking(false)
      }
    },
    [ids, onApply, load],
  )

  if (!data || (!rows.length && !data.enabled)) return null

  return (
    <AnimatePresence initial={false}>
      <m.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={springFor()}
      >
        <Section
          title="Waiting for your approval"
          description={
            rows.length
              ? `The agent shortlisted these. Nothing is submitted until you approve.`
              : `Auto Apply is on. Nothing has cleared the bar yet.`
          }
          flush={rows.length > 0}
          actions={
            <Status tone={rows.length ? 'warn' : 'neutral'}>
              {data.spentToday} of {data.dailyCap} today
            </Status>
          }
        >
          {error ? (
            <div className="p-4">
              <Note tone="bad" title="Could not update the queue" onDismiss={() => setError('')}>
                {error}
              </Note>
            </div>
          ) : null}

          {!rows.length ? null : (
            <>
              <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
                <span className="text-tiny text-n-300">
                  {ids.length} of {rows.length} selected
                </span>
                <Button
                  size="sm"
                  variant="primary"
                  disabled={busy || working || !ids.length}
                  onClick={() => decide('approved')}
                >
                  Approve and apply
                </Button>
                <Button
                  size="sm"
                  disabled={busy || working || !ids.length}
                  onClick={() => decide('rejected')}
                >
                  Not these
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setChosen(new Set())}>
                  Clear
                </Button>
              </div>

              <Table
                columns={[
                  { label: '', className: 'w-8' },
                  { label: 'Role' },
                  { label: 'Company' },
                  { label: 'Score' },
                  { label: 'Why' },
                ]}
                rows={rows}
                empty={<Empty title="Nothing waiting" />}
                renderRow={(r) => (
                  <Tr key={r.id}>
                    <Td>
                      <input
                        type="checkbox"
                        checked={chosen.has(r.id)}
                        onChange={() =>
                          setChosen((prev) => {
                            const next = new Set(prev)
                            next.has(r.id) ? next.delete(r.id) : next.add(r.id)
                            return next
                          })
                        }
                        aria-label={`Include ${r.title}`}
                        className="size-4 accent-blue-500"
                      />
                    </Td>
                    <Td className="max-w-[20rem]">
                      <a
                        href={r.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sm font-medium text-n-100 hover:text-blue-500"
                      >
                        {r.title}
                      </a>
                      {r.role_category ? (
                        <Tag className="ml-2">{r.role_category.replace(/_/g, ' ')}</Tag>
                      ) : null}
                    </Td>
                    <Td className="max-w-[11rem] truncate text-n-400" title={r.company_name || ''}>
                      {r.company_name || '—'}
                    </Td>
                    <Td className="tabular-nums text-n-300">
                      {r.fit_score ? Math.round(r.fit_score) : '—'}
                    </Td>
                    <Td className="max-w-[22rem] text-tiny leading-snug text-n-500">
                      {r.proposal_reason || ''}
                    </Td>
                  </Tr>
                )}
              />
            </>
          )}
        </Section>
      </m.div>
    </AnimatePresence>
  )
}
