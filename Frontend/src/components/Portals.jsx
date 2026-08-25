import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Disclosure, Empty, Status, Table, Td, Tr } from './ui'

/*
  What Jobenzy can do with each applicant tracking system.

  Reading a board and submitting to it are shown as separate columns because
  they are separate capabilities: a role can be perfectly discoverable through
  a system whose form nobody has ever got through. Saying so here means the
  user knows what to expect before pressing Apply, rather than finding out
  from a failure.

  "Unproven" is deliberately not "no". The generic driver handles most standard
  forms; nobody has simply watched it succeed on that system yet.
*/

const SUBMIT_TONE = {
  proven: 'ok',
  likely: 'accent',
  unproven: 'neutral',
  no: 'warn',
}

const SUBMIT_LABEL = {
  proven: 'proven',
  likely: 'likely',
  unproven: 'untested',
  no: 'via the employer',
}

export default function Portals({ open, onToggle }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    if (!open || data) return
    api
      .agentPortals()
      .then(setData)
      .catch(() => setData({ rows: [], summary: {} }))
  }, [open, data])

  const s = data?.summary || {}

  return (
    <Disclosure
      title="Application systems"
      description={
        data
          ? `${s.detects} of ${s.total} readable · ${s.proven} proven for submitting`
          : 'Which portals Jobenzy can read, and which it can submit to.'
      }
      open={open}
      onToggle={onToggle}
    >
      {!data ? (
        <Empty title="Loading" />
      ) : (
        <>
          <p className="mb-3 text-tiny leading-relaxed text-n-400">
            Reading a board and submitting to it are separate capabilities. A role can be
            perfectly discoverable through a system whose form has never been tested — that
            is what <span className="text-n-300">untested</span> means, and it is not the
            same as no.
          </p>
          <Table
            columns={[{ label: 'System' }, { label: 'Finds jobs' }, { label: 'Submits' }, { label: '' }]}
            rows={data.rows}
            maxHeight="max-h-[26rem]"
            empty={<Empty title="No systems listed" />}
            renderRow={(p) => (
              <Tr key={p.slug}>
                <Td className="text-n-200">{p.name}</Td>
                <Td>
                  {p.detects ? (
                    <Status tone="ok">yes</Status>
                  ) : (
                    <Status tone="neutral" dot={false}>
                      no public board
                    </Status>
                  )}
                </Td>
                <Td>
                  <Status tone={SUBMIT_TONE[p.submits] || 'neutral'} dot={p.submits === 'proven'}>
                    {SUBMIT_LABEL[p.submits] || p.submits}
                  </Status>
                </Td>
                <Td className="max-w-[24rem] text-tiny leading-snug text-n-500">
                  {p.note || ''}
                </Td>
              </Tr>
            )}
          />
        </>
      )}
    </Disclosure>
  )
}
