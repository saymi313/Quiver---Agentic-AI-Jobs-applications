import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Button, Disclosure, Field, Input, Note, Status } from './ui'

/*
  Logins for the sites that will not show a form without an account.

  Workday and iCIMS are the two that stop the applier cold: both make you sign
  in, or register, before the application even appears. This is where the account
  goes — a per-site username and password, plus a shared application password for
  the accounts the agent has to create itself.

  What matters here is what the panel never shows. The passwords live in
  `Backend/credentials.json`, outside the repo and outside the settings the API
  hands back; this screen only ever reports that a password is set, and the one
  time it shows a generated one, it says so and does not keep it.
*/

export default function Credentials({ open, onToggle }) {
  const [state, setState] = useState(null)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ domain: '', username: '', password: '' })
  const [appPw, setAppPw] = useState('')
  const [generated, setGenerated] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(
    () => api.agentCredentials().then(setState).catch((e) => setError(e.message)),
    [],
  )
  useEffect(() => {
    if (open) load()
  }, [open, load])

  const act = async (fn) => {
    setBusy(true)
    setError('')
    try {
      const r = await fn()
      if (r) setState(r)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const domains = state?.domains || []
  const summary = state
    ? `${domains.length} site${domains.length === 1 ? '' : 's'}${
        state.hasApplicationPassword ? ' · application password set' : ''
      }`
    : 'Logins for sites that need an account before they show a form.'

  return (
    <Disclosure
      title="Employer accounts"
      description={summary}
      open={open}
      onToggle={onToggle}
      actions={
        state?.hasApplicationPassword ? <Status tone="ok">app password set</Status> : null
      }
    >
      {error ? (
        <div className="pb-3">
          <Note tone="bad" title="Could not save" onDismiss={() => setError('')}>{error}</Note>
        </div>
      ) : null}

      {/* stored sites */}
      {domains.length ? (
        <ul className="mb-4 divide-y divide-line rounded-md border border-line">
          {domains.map((d) => (
            <li key={d.domain} className="flex items-center gap-3 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-n-100">{d.domain}</p>
                <p className="truncate text-micro text-n-500">{d.username}</p>
              </div>
              <Status tone={d.hasPassword ? 'ok' : 'warn'} dot={false}>
                {d.hasPassword ? 'saved' : 'no password'}
              </Status>
              <button
                onClick={() => act(() => api.agentDeleteCredential(d.domain))}
                className="press text-tiny text-n-500 hover:text-bad-400"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {/* add a site */}
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Site domain">
          <Input
            value={form.domain}
            onChange={(e) => setForm((f) => ({ ...f, domain: e.target.value }))}
            placeholder="acme.wd1.myworkdayjobs.com"
          />
        </Field>
        <Field label="Username or email">
          <Input
            value={form.username}
            onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
            placeholder="you@email.com"
          />
        </Field>
        <Field label="Password">
          <Input
            type="password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            placeholder="••••••••"
          />
        </Field>
      </div>
      <div className="mt-3">
        <Button
          size="sm"
          variant="primary"
          busy={busy}
          disabled={!form.domain.trim() || !form.username.trim() || !form.password.trim()}
          onClick={() =>
            act(() => api.agentSetCredential(form.domain.trim(), form.username.trim(), form.password))
              .then(() => setForm({ domain: '', username: '', password: '' }))
          }
        >
          Save login
        </Button>
      </div>

      {/* the shared application password */}
      <div className="mt-5 rounded-md border border-line bg-raised p-3">
        <p className="text-sm font-medium text-n-100">Application password</p>
        <p className="mt-0.5 text-micro leading-relaxed text-n-500">
          Used for the accounts the agent registers when a site demands one, so your real passwords
          never do. Set it once, or let Quiver generate a strong one.
        </p>
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          <div className="min-w-[12rem] flex-1">
            <Input
              type="password"
              value={appPw}
              onChange={(e) => setAppPw(e.target.value)}
              placeholder={state?.hasApplicationPassword ? 'replace the current one' : 'set a password'}
            />
          </div>
          <Button size="sm" disabled={!appPw.trim() || busy}
                  onClick={() => act(() => api.agentSetAppPassword({ password: appPw }))
                    .then(() => setAppPw(''))}>
            Save
          </Button>
          <Button size="sm" variant="ghost" busy={busy}
                  onClick={() =>
                    act(async () => {
                      const r = await api.agentSetAppPassword({ generate: true })
                      setGenerated(r.generated || '')
                      return r
                    })}>
            Generate one
          </Button>
        </div>
        {generated ? (
          <Note tone="warn" title="Write this down now" onDismiss={() => setGenerated('')}>
            <code className="text-n-100">{generated}</code> — this is the only time it is shown.
          </Note>
        ) : null}
      </div>
    </Disclosure>
  )
}
