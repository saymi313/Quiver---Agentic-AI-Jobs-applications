import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { CategoryChip, MessageChip, SidePanel } from './apple'
import QuickReply from './QuickReply'
import { Note, Status } from './ui'

/*
  A message, opened to read in full.

  The list shows a snippet; this shows the whole thing, because a rejection you
  can only half-read is a rejection you have to leave for Gmail. Opening it marks
  it read — answering a message is the clearest possible signal you have seen it,
  and so is opening one — and the reply box is right here, threaded onto the
  original, so the loop closes without a context switch.
*/

const CLASS_LABEL = {
  acknowledgment: 'Acknowledged',
  interview: 'Interview',
  assessment: 'Assessment',
  offer: 'Offer',
  rejection: 'Rejection',
  reminder: 'Reminder',
  verification: 'Verification',
  bounce: 'Bounced',
  other: 'Everything else',
}

function when(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export default function MessageReader({ messageId, onClose, onChanged }) {
  const [msg, setMsg] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!messageId) {
      setMsg(null)
      return
    }
    let alive = true
    setMsg(null)
    setError('')
    api
      .agentMessage(messageId)
      .then((d) => {
        if (!alive) return
        setMsg(d.message)
        onChanged?.() // opening marked it read; refresh the unread badge
      })
      .catch((e) => alive && setError(e.message))
    return () => {
      alive = false
    }
    // onChanged intentionally omitted: it changes each render and would re-fetch
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messageId])

  return (
    <SidePanel
      open={!!messageId}
      onClose={onClose}
      title={msg?.subject || (error ? 'Could not open' : 'Loading…')}
      subtitle={msg ? `${msg.from_addr}${msg.received_at ? ` · ${when(msg.received_at)}` : ''}` : undefined}
      badge={
        msg ? (
          <div className="flex flex-wrap items-center gap-2">
            <MessageChip klass={msg.klass} label={CLASS_LABEL[msg.klass]} />
            {msg.company_name ? (
              <span className="text-micro text-n-500">
                {msg.company_name}
                {msg.title ? ` — ${msg.title}` : ''}
              </span>
            ) : (
              <Status tone="warn" dot={false}>
                not matched to an application
              </Status>
            )}
            {msg.role_category ? <CategoryChip slug={msg.role_category} /> : null}
          </div>
        ) : null
      }
      footer={msg ? <QuickReply message={msg} onSent={onChanged} /> : null}
    >
      {error ? (
        <Note tone="bad" title="Could not open the message">
          {error}
        </Note>
      ) : !msg ? (
        <p className="text-tiny text-n-500">Loading the message…</p>
      ) : (
        <div className="whitespace-pre-line text-sm leading-relaxed text-n-200">
          {(msg.body || msg.snippet || '').trim() || 'This message has no readable text.'}
        </div>
      )}
    </SidePanel>
  )
}
