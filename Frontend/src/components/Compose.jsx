import { useState } from 'react'
import { api } from '../lib/api'
import { Sheet } from './apple'
import { Button, Field, Input, Note, Textarea } from './ui'

/*
  A new message, sent from where the replies are read.

  The mailbox is already open in front of the user; sending a follow-up or a
  thank-you from the same place, over the same credentials, saves the trip to
  Gmail that a single line never justifies. This starts a fresh thread — the
  reply box under a message is the way to answer one that already exists.
*/

export default function Compose({ open, onClose, onSent }) {
  const [to, setTo] = useState('')
  const [subject, setSubject] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const reset = () => {
    setTo('')
    setSubject('')
    setText('')
    setError('')
  }

  const send = () => {
    setBusy(true)
    setError('')
    api
      .agentCompose(to.trim(), subject.trim(), text.trim())
      .then((r) => {
        reset()
        onSent?.(r)
        onClose?.()
      })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false))
  }

  const ready = /.+@.+\..+/.test(to.trim()) && text.trim()

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="New message"
      description="Sent over your own mailbox. It starts a new thread."
      footer={
        <div className="flex items-center gap-2">
          <Button variant="primary" busy={busy} disabled={!ready} onClick={send}>
            Send
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </div>
      }
    >
      <div className="space-y-3">
        {error ? (
          <Note tone="bad" title="Could not send" onDismiss={() => setError('')}>
            {error}
          </Note>
        ) : null}
        <Field label="To">
          <Input
            type="email"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            placeholder="recruiter@company.com"
          />
        </Field>
        <Field label="Subject">
          <Input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="(optional)"
          />
        </Field>
        <Field label="Message">
          <Textarea
            rows={8}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Write your message…"
          />
        </Field>
      </div>
    </Sheet>
  )
}
