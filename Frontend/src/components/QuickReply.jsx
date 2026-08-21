import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion as m } from 'motion/react'
import { api } from '../lib/api'
import { springFor } from '../lib/motion'
import { Button, Icon, Note, Textarea } from './ui'

/*
  Answering a reply, where the reply is.

  The mailbox is read here so that an interview invitation is not sitting
  unseen; making the user leave for Gmail to type "Tuesday at 3 works" is where
  that stops being useful. The reply threads onto the original by Message-ID,
  so it joins the conversation rather than arriving as a new mail with a "Re:"
  subject.

  The openers below are openers, not templates to send unread. Each leaves the
  cursor at the end of a sentence that is deliberately unfinished, because the
  useful half of the answer is the part only the user can write.
*/

const OPENERS = {
  interview: [
    ['Accept', 'Thank you — that works for me. '],
    ['Ask for another time', 'Thank you for the invitation. I have a conflict then — could we look at '],
  ],
  assessment: [
    ['Confirm', 'Thank you — I will complete it and send it back by '],
    ['Ask for detail', 'Thank you. Before I start, could you tell me '],
  ],
  offer: [
    ['Thank them', 'Thank you very much — I am glad to hear it. '],
    ['Ask for time', 'Thank you very much. Could I have until '],
  ],
  rejection: [
    ['Thank them', 'Thank you for letting me know, and for the time your team spent. '],
    ['Ask for feedback', 'Thank you for letting me know. If you have a moment, I would value '],
  ],
  default: [['Reply', '']],
}

export default function QuickReply({ message, onSent }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(null)
  const box = useRef(null)

  useEffect(() => {
    if (open) box.current?.focus()
  }, [open])

  const openers = OPENERS[message.klass] || OPENERS.default

  const send = () => {
    if (!text.trim()) return
    setBusy(true)
    setError('')
    api
      .agentReply(message.id, text.trim())
      .then((r) => {
        setSent(r)
        setText('')
        setOpen(false)
        onSent?.()
      })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false))
  }

  const start = (opener) => {
    setText(opener)
    setOpen(true)
  }

  if (!message.from_addr) return null

  return (
    <div className="mt-2">
      {sent ? (
        <p className="text-micro text-ok-400">
          Replied to {sent.to}
          {sent.threaded ? ' in the same thread' : ''}.
        </p>
      ) : null}

      {!open ? (
        <div className="flex flex-wrap items-center gap-1.5">
          {openers.map(([label, opener]) => (
            <button
              key={label}
              onClick={() => start(opener)}
              className="press inline-flex items-center gap-1 rounded-full bg-n-850 px-2.5 py-1
                text-micro font-medium text-n-300 hover:bg-n-800 hover:text-n-100"
            >
              <Icon.Reply className="size-3" />
              {label}
            </button>
          ))}
        </div>
      ) : null}

      <AnimatePresence initial={false}>
        {open ? (
          <m.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={springFor()}
            className="overflow-hidden"
          >
            <div className="space-y-2 pt-1">
              <Textarea
                ref={box}
                rows={4}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={`Reply to ${message.from_addr}`}
                aria-label={`Reply to ${message.subject || 'this message'}`}
              />
              {error ? (
                <Note tone="bad" title="Could not send" onDismiss={() => setError('')}>
                  {error}
                </Note>
              ) : null}
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" variant="primary" busy={busy} disabled={!text.trim()}
                        onClick={send}>
                  Send reply
                </Button>
                <Button size="sm" variant="ghost" onClick={() => { setOpen(false); setError('') }}>
                  Cancel
                </Button>
                <span className="text-micro text-n-500">
                  Goes to {message.from_addr} in the same thread.
                </span>
              </div>
            </div>
          </m.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}
