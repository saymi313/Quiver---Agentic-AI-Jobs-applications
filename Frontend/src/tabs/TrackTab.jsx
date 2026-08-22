import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion as m } from 'motion/react'
import { api } from '../lib/api'
import { springFor } from '../lib/motion'
import { useJobStream } from '../lib/useJobStream'
import Console from '../components/Console'
import Kanban from '../components/Kanban'
import MessageReader from '../components/MessageReader'
import Compose from '../components/Compose'
import AddApplication from '../components/AddApplication'
import ClearData from '../components/ClearData'
import { MessageChip, Segmented, StageBar } from '../components/apple'
import {
  Button,
  Empty,
  Icon,
  Input,
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
  { key: 'applied', label: 'Applied', tone: 'blue' },
  { key: 'interviewing', label: 'Interviewing', tone: 'blue' },
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
  // Which panels are open, and how the pipeline is shown.
  const [view, setView] = useState('board')
  const [reading, setReading] = useState(null) // message id in the reader
  const [composing, setComposing] = useState(false)
  const [adding, setAdding] = useState(false)
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')

  // Debounce the inbox search so a query fires once the typing settles.
  useEffect(() => {
    const t = setTimeout(() => setQ(search), 300)
    return () => clearTimeout(t)
  }, [search])

  const refresh = useCallback(() => {
    setError('')
    return Promise.all([
      api.agentTracker(),
      api.agentInbox({ klass: klass || undefined, q: q || undefined }),
    ])
      .then(([t, i]) => {
        setTracker(t)
        setInbox(i)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [klass, q])

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
          <div className="flex items-center gap-3">
            <ClearData kind="tracker" onCleared={refresh} />
            <Button
              variant="primary"
              disabled={busy || !mailbox?.available}
              busy={stream.starting === 'agent_inbox'}
              onClick={() => stream.start({ key: 'agent_inbox', limit: 100, max_age: 21 })}
            >
              Read replies
            </Button>
          </div>
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
        {/* The count answers "how many"; the bar answers "what proportion",
            which is the question you actually have when scanning five stages
            at once. */}
        <div className="grid gap-5 sm:grid-cols-3 lg:grid-cols-5">
          {STAGES.map((stage) => (
            <StageBar
              key={stage.key}
              label={stage.label}
              value={counts[stage.key] ?? 0}
              total={rows.length || 1}
              tone={stage.tone}
              hint={stage.key === 'ghosted' ? 'no reply' : undefined}
            />
          ))}
        </div>

        {/* The two numbers a pipeline is judged on: how often an application
            drew any reply, and how often it reached a conversation. */}
        {tracker?.rates?.total ? (
          <div className="mt-4 flex flex-wrap gap-x-8 gap-y-2 border-t border-line pt-3">
            <span className="text-tiny text-n-400">
              <span className="font-semibold tabular-nums text-n-100">
                {tracker.rates.replyRate}%
              </span>{' '}
              reply rate
              <span className="text-n-500"> · {tracker.rates.replied} of {tracker.rates.total}</span>
            </span>
            <span className="text-tiny text-n-400">
              <span className="font-semibold tabular-nums text-n-100">
                {tracker.rates.interviewRate}%
              </span>{' '}
              reached a conversation
              <span className="text-n-500"> · {tracker.rates.interviews} of {tracker.rates.total}</span>
            </span>
            {tracker.rates.offers ? (
              <span className="text-tiny text-ok-400">
                <span className="font-semibold tabular-nums">{tracker.rates.offers}</span> offer
                {tracker.rates.offers === 1 ? '' : 's'}
              </span>
            ) : null}
          </div>
        ) : null}
      </Section>

      {/* --------------------------------------------------- applications */}
      <Section
        title="Applications"
        description="Drag a card between columns, or set a stage by hand — the agent never overrules it."
        flush
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Segmented
              size="sm"
              ariaLabel="Pipeline view"
              value={view}
              onChange={setView}
              options={[
                { value: 'board', label: 'Board' },
                { value: 'table', label: 'Table' },
              ]}
            />
            <Button size="sm" onClick={() => setAdding(true)}>
              <Icon.Plus />
              Add
            </Button>
            <a
              href={api.agentExportApplicationsUrl()}
              className="press inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-tiny
                font-medium text-n-400 ring-1 ring-line hover:text-n-100"
            >
              <Icon.Download />
              Export
            </a>
          </div>
        }
      >
        {loading && !tracker ? (
          <Empty title="Loading" />
        ) : view === 'board' ? (
          rows.length ? (
            <div className="p-4">
              <Kanban
                columns={STAGES.map((s) => ({
                  key: s.key,
                  label: s.label,
                  tone: s.key === 'offer' ? 'ok' : s.key === 'rejected' ? 'bad'
                    : s.key === 'ghosted' ? 'neutral' : 'accent',
                }))}
                cards={rows.map((r) => ({ ...r, stage: r.tracker_status || 'applied' }))}
                onMove={(id, stage) =>
                  api.agentSetStage(id, stage).then(refresh).catch((e) => setError(e.message))
                }
              />
            </div>
          ) : (
            <Empty title="Nothing applied yet">
              Applications appear here once one is submitted from the Jobs screen, or add one by
              hand.
            </Empty>
          )
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
                      className="text-sm font-medium text-n-100 hover:text-blue-500"
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
        description="Open one to read it in full and answer in the same thread."
        flush
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="w-40">
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search"
                aria-label="Search messages"
                className="h-8 py-0"
              />
            </div>
            <div className="w-40">
              <Select
                value={klass}
                onChange={(e) => setKlass(e.target.value)}
                aria-label="Filter replies by kind"
                className="h-8 py-0"
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
            <Button size="sm" onClick={() => setComposing(true)}>
              <Icon.Send className="size-3.5" />
              Compose
            </Button>
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
                >
                  {/* The whole row opens the message — reading it in full and
                      replying happen in the panel, not inline. An unread one
                      keeps a dot and full contrast until it is opened. */}
                  <button
                    onClick={() => setReading(msg.id)}
                    className={`press block w-full px-4 py-3 text-left hover:bg-raised ${
                      msg.read_at ? 'opacity-60' : ''
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      {!msg.read_at ? (
                        <span className="size-1.5 shrink-0 rounded-full bg-blue-500" />
                      ) : null}
                      <MessageChip klass={msg.klass} label={CLASS_LABEL[msg.klass]} />
                      <span className="min-w-0 flex-1 truncate text-sm text-n-200">
                        {msg.subject || '(no subject)'}
                      </span>
                      <span className="shrink-0 text-tiny text-n-500">{when(msg.received_at)}</span>
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
                        <span className="text-warn-400"> · not matched to an application</span>
                      )}
                    </p>
                    {msg.snippet ? (
                      <p className="mt-1 line-clamp-1 text-tiny leading-relaxed text-n-400">
                        {msg.snippet}
                      </p>
                    ) : null}
                  </button>
                </m.li>
              ))}
            </AnimatePresence>
          </ul>
        )}
      </Section>

      <Console lines={stream.lines} job={stream.job} onStop={stream.stop} onClear={stream.clear} />

      <MessageReader messageId={reading} onClose={() => setReading(null)} onChanged={refresh} />
      <Compose open={composing} onClose={() => setComposing(false)} onSent={refresh} />
      <AddApplication open={adding} onClose={() => setAdding(false)} onAdded={refresh} />
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
