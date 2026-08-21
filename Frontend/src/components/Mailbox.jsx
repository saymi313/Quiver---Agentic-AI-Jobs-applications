import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Disclosure, Metric, Note, Status } from './ui'

/*
  The mailbox, as a connection you can see the state of.

  Quiver reads replies over IMAP with the same Gmail app password the outreach
  sender already uses — one credential, no OAuth, nothing hosted. That is worth
  saying plainly on the settings page, because "connect your mailbox" usually
  means handing an account to somebody else's server, and here it does not.

  The panel reports rather than configures: the credential itself lives in
  `Backend/.env`, which is the right place for a password and the wrong place
  for a web form to be writing to.
*/

export default function Mailbox({ open, onToggle }) {
  const [state, setState] = useState(null)

  const load = useCallback(
    () => api.agentMailbox().then(setState).catch((e) => setState({ error: e.message })),
    [],
  )
  useEffect(() => { if (open) load() }, [open, load])

  const connected = state?.connected

  return (
    <Disclosure
      title="Mailbox"
      description={
        state
          ? connected
            ? `${state.address} · ${state.messages ?? 0} messages read, ${state.linked ?? 0} matched to an application`
            : 'Not connected — replies cannot be read or sent.'
          : 'Where replies are read from, and sent from.'
      }
      open={open}
      onToggle={onToggle}
      actions={
        state ? (
          <Status tone={connected ? 'ok' : 'warn'}>{connected ? 'connected' : 'not set up'}</Status>
        ) : null
      }
    >
      {!state ? (
        <p className="text-tiny text-n-500">Checking…</p>
      ) : connected ? (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
            <Metric label="Messages" value={state.messages ?? 0} hint="read into Track" />
            <Metric label="Matched" value={state.linked ?? 0} hint="tied to an application" />
            <Metric label="Unread" value={state.unread ?? 0} hint="waiting on you" />
            <Metric
              label="Latest"
              value={state.lastAt ? new Date(state.lastAt).toLocaleDateString() : '—'}
              hint="most recent reply"
            />
          </dl>
          <p className="text-tiny leading-relaxed text-n-500">
            Reading and replying both use the Gmail app password in{' '}
            <code className="text-n-300">Backend/.env</code>. Replies thread onto the original
            message, so they land in the same conversation rather than arriving as a new mail.
            Nothing is sent without you writing it.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <Note tone="warn" title="No mailbox credentials">
            {state.reason || state.error}
          </Note>
          <ol className="ml-4 list-decimal space-y-1.5 text-tiny leading-relaxed text-n-400">
            <li>
              Turn on 2-step verification for the Google account, then create an app password
              under Security → App passwords.
            </li>
            <li>
              Put it in <code className="text-n-300">Backend/.env</code> as{' '}
              <code className="text-n-300">GMAIL_ADDRESS</code> and{' '}
              <code className="text-n-300">GMAIL_APP_PASS</code>.
            </li>
            <li>
              Enable IMAP in Gmail under Settings → Forwarding and POP/IMAP, then restart the
              backend.
            </li>
          </ol>
        </div>
      )}
    </Disclosure>
  )
}
