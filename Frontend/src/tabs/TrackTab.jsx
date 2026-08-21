import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion as m } from 'motion/react'
import { api } from '../lib/api'
import { springFor } from '../lib/motion'
import { useJobStream } from '../lib/useJobStream'
import Console from '../components/Console'
import {
  Button,
  Empty,
  Icon,
  Metric,
  Note,
  PageHead,
  Section,
  Select,
  Status,
  Table,
  Tag,
  Td,
  Tr,
} from '../components/ui'

/*
  Track — what happened after you applied.

  Two questions, two panels. The pipeline answers "where does everything
  stand"; the inbox answers "what did they actually say". They are stacked
  rather than side by side because the second is how you check the first.

  Nothing here changes a stage on its own. The agent advances a stage only on
  a confident link, and any value set here by hand outranks it permanently.
*/

const STAGES = [
  { key: 'applied', label: 'Applied', tone: 'info' },
  { key: 'interviewing', label: 'Interviewing', tone: 'accent' },
  { key: 'offer', label: 'Offer', tone: 'ok' },
  { key: 'rejected', label: 'Rejected', tone: 'bad' },
  { key: 'ghosted', label: 'Ghosted', tone: 'neutral' },
]

const CLASS_LABEL = {
  acknowledgment: 'Acknowledged',
  interview: 'Interviews',
  assessment: 'Assessments',
  offer: 'Offers',
  rejection: 'Rejections',
  reminder: 'Reminders',
  verification: 'Verification',
  bounce: 'Bounced',
  other: 'Everything else',
}

const CLASS_TONE = {
  interview: 'accent',
  assessment: 'accent',
  offer: 'ok',
  rejection: 'bad',
  bounce: 'warn',
  reminder: 'warn',
}

function when(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const mins = Math.floor((Date.now() - d.getTime()) / 60000)
  if (mins < 60) return mins <= 1 ? 'just now' : `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return d.toLocaleDateString()
}

export default function TrackTab() {
  const [tracker, setTracker] = useState(null)
  const [inbox, setInbox] = useState(null)
  const [klass, setKlass] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = useCallback(() => {
    setError('')
    return Promise.all([api.agentTracker(), api.agentInbox({ klass: klass || undefined })])
      .then(([t, i]) => {
        setTracker(t)
        setInbox(i)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [klass])

  useEffect(() => {
    refresh()
  }, [refresh])

  const stream = useJobStream(refresh)
  const busy = stream.busy || !!stream.starting

  const counts = tracker?.counts || {}
  const mailbox = tracker?.mailbox
  const rows = tracker?.rows || []
  const messages = inbox?.rows || []

  return (
    <div className="space-y-4">
      <PageHead
        title="Track"
        description="Every application that reached an employer, and what came back. Replies are matched to the application they belong to and the stage moves on its own."
        actions={
          <Button
            variant="primary"
            disabled={busy || !mailbox?.available}
            busy={stream.starting === 'agent_inbox'}
            onClick={() => stream.start({ key: 'agent_inbox', limit: 100, max_age: 21 })}
          >
            Read replies
          </Button>
        }
      />

      {error ? (
        <Note tone="bad" title="Could not load the tracker" onDismiss={() => setError('')}>
          {error}
        </Note>
      ) : null}

      {mailbox && !mailbox.available ? (
        <Note tone="warn" title="The mailbox is not connected">
          {mailbox.reason}
        </Note>
      ) : null}

      {/* ------------------------------------------------------- pipeline */}
      <Section
        title="Pipeline"
        description={
          tracker
            ? `${rows.length} application${rows.length === 1 ? '' : 's'} reached an employer.`
            : 'Where everything stands.'
        }
        actions={
          inbox?.unread ? <Status tone="accent">{inbox.unread} unread</Status> : null
        }
      >
        <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {STAGES.map((s) => (
            <Metric
              key={s.key}
              label={s.label}
              value={counts[s.key] ?? 0}
              hint={s.key === 'ghosted' ? 'no reply' : undefined}
            />
          ))}
        </div>
      </Section>

      {/* --------------------------------------------------- applications */}
      <Section title="Applications" description="Set a stage by hand and the agent will not overrule it." flush>
        {loading && !tracker ? (
          <Empty title="Loading" />
        ) : (
          <Table
            columns={[
              { label: 'Role' },
              { label: 'Company' },
              { label: 'Applied' },
              { label: 'Last reply' },
              { label: 'Replies' },
              { label: 'Stage', className: 'w-40' },
            ]}
            rows={rows}
            empty={
              <Empty title="Nothing applied yet">
                Applications appear here once one is submitted from the Jobs screen.
              </Empty>
            }
            renderRow={(r) => (
              <Tr key={r.id}>
                <Td className="max-w-[20rem]">
                  {r.url ? (
                    <a
                      href={r.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm text-n-200 hover:text-brand-400"
                    >
                      {r.title || 'Untitled role'}
                    </a>
                  ) : (
                    <span className="text-sm text-n-200">{r.title || 'Untitled role'}</span>
                  )}
                  {r.dry_run ? <Tag className="ml-2">dry run</Tag> : null}
                </Td>
                <Td className="max-w-[11rem] truncate text-n-400" title={r.company_name || ''}>
                  {r.company_name || '—'}
                </Td>
                <Td className="whitespace-nowrap text-n-500">{when(r.submitted_at)}</Td>
                <Td className="whitespace-nowrap text-n-500">{when(r.last_message_at)}</Td>
                <Td className="text-n-500">{r.message_count || 0}</Td>
                <Td>
                  <StagePicker
                    value={r.tracker_status || 'applied'}
                    onChange={(next) =>
                      api
                        .agentSetStage(r.id, next)
                        .then(refresh)
                        .catch((e) => setError(e.message))
                    }
                  />
                </Td>
              </Tr>
            )}
          />
        )}
      </Section>

      {/* ------------------------------------------------------ the inbox */}
      <Section
        title="Replies"
        description="Matched to an application where the link is certain enough to trust."
        flush
        actions={
          <div className="w-48">
            <Select
              value={klass}
              onChange={(e) => setKlass(e.target.value)}
              aria-label="Filter replies by kind"
            >
              <option value="">Everything</option>
              {Object.entries(CLASS_LABEL).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                  {inbox?.counts?.[key] ? ` (${inbox.counts[key]})` : ''}
                </option>
              ))}
            </Select>
          </div>
        }
      >
        {messages.length === 0 ? (
          <div className="p-4">
            <Empty title="No replies yet">
              {mailbox?.available
                ? 'Press "Read replies" to check the mailbox.'
                : 'Connect the mailbox to see employer replies here.'}
            </Empty>
          </div>
        ) : (
          <ul className="divide-y divide-line">
            <AnimatePresence initial={false}>
              {messages.map((msg) => (
                <m.li
                  key={msg.id}
                  layout
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={springFor()}
                  className={`px-4 py-3 ${msg.read_at ? 'opacity-60' : ''}`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Status tone={CLASS_TONE[msg.klass] || 'neutral'} dot={false}>
                      {CLASS_LABEL[msg.klass] || msg.klass || 'unsorted'}
                    </Status>
                    <span className="min-w-0 flex-1 truncate text-sm text-n-200">
                      {msg.subject || '(no subject)'}
                    </span>
                    <span className="shrink-0 text-tiny text-n-500">
                      {when(msg.received_at)}
                    </span>
                    <button
                      className="press shrink-0 text-tiny text-n-500 hover:text-n-200"
                      onClick={() =>
                        api.agentMarkRead(msg.id, !msg.read_at).then(refresh).catch(() => {})
                      }
                    >
                      {msg.read_at ? 'unread' : 'read'}
                    </button>
                  </div>
                  <p className="mt-1 text-tiny text-n-500">
                    {msg.from_addr}
                    {msg.company_name ? (
                      <>
                        {' · '}
                        <span className="text-n-400">{msg.company_name}</span>
                        {msg.title ? ` — ${msg.title}` : ''}
                      </>
                    ) : (
                      // An unmatched message is worth saying so about: it is
                      // the difference between "no reply" and "a reply we
                      // could not place".
                      <span className="text-warn-400"> · not matched to an application</span>
                    )}
                  </p>
                  {msg.snippet ? (
                    <p className="mt-1 line-clamp-2 text-tiny leading-relaxed text-n-400">
                      {msg.snippet}
                    </p>
                  ) : null}
                </m.li>
              ))}
            </AnimatePresence>
          </ul>
        )}
      </Section>

      <Console lines={stream.lines} job={stream.job} onStop={stream.stop} onClear={stream.clear} />
    </div>
  )
}

/** The stage control. A select rather than a row of buttons: five mutually
 *  exclusive values with one current, which is exactly what a select is. */
function StagePicker({ value, onChange }) {
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Pipeline stage">
      {STAGES.map((s) => (
        <option key={s.key} value={s.key}>
          {s.label}
        </option>
      ))}
    </Select>
  )
}
