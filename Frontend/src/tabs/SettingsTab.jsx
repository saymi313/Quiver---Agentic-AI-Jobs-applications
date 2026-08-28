import { useCallback, useEffect, useState } from 'react'
import { motion as m } from 'motion/react'
import { springFor } from '../lib/motion'
import { api } from '../lib/api'
import Settings from '../components/Settings'
import Portals from '../components/Portals'
import Mailbox from '../components/Mailbox'
import Credentials from '../components/Credentials'
import SavedAnswers from '../components/SavedAnswers'
import {
  Button, Checkbox, Disclosure, Empty, Field, Input, Note, PageHead,
} from '../components/ui'

/*
  Settings — everything that configures the agent on the screen it belongs on.
*/

export default function SettingsTab() {
  const [overview, setOverview] = useState(null)
  const [panel, setPanel] = useState('search')

  const refresh = useCallback(
    () => api.agentOverview().then(setOverview).catch(() => setOverview(null)),
    [],
  )
  useEffect(() => { refresh() }, [refresh])

  if (!overview) return <Empty title="Loading" />

  return (
    <div className="space-y-4">
      <PageHead
        title="Settings"
        description="What the agent searches for, which application systems it can reach, the answers it puts in forms, and the mailbox it reads replies from."
      />

      <ProfileCompleteness data={overview.profileCompleteness} onEdit={() => setPanel('agent')} />

      <Portals
        open={panel === 'search'}
        onToggle={(v) => setPanel(v ? 'search' : '')}
        overview={overview}
        onSaved={refresh}
      />

      <Mailbox open={panel === 'mailbox'} onToggle={(v) => setPanel(v ? 'mailbox' : '')} />

      <Credentials open={panel === 'accounts'} onToggle={(v) => setPanel(v ? 'accounts' : '')} />

      <SavedAnswers
        overview={overview}
        onSaved={refresh}
        open={panel === 'answers'}
        onToggle={(v) => setPanel(v ? 'answers' : '')}
      />

      <Notifications
        overview={overview}
        onSaved={refresh}
        open={panel === 'notify'}
        onToggle={(v) => setPanel(v ? 'notify' : '')}
      />

      <Settings
        overview={overview}
        onSaved={refresh}
        open={panel === 'agent'}
        onToggle={(v) => setPanel(v ? 'agent' : '')}
      />
    </div>
  )
}

function Notifications({ overview, onSaved, open, onToggle }) {
  const saved = overview.settings.notify || {}
  const [form, setForm] = useState({
    enabled: saved.enabled ?? true,
    desktop: saved.desktop ?? true,
    email: saved.email ?? false,
    min_score: saved.min_score ?? 75,
  })
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  const set = (patch) => {
    setForm((f) => ({ ...f, ...patch }))
    setDone(false)
  }

  const save = () => {
    setBusy(true)
    api
      .agentSettings({ notify: { ...form, min_score: Number(form.min_score) || 75 } })
      .then(() => { setDone(true); onSaved?.() })
      .finally(() => setBusy(false))
  }

  const desktopBlocked = typeof Notification !== 'undefined' && Notification.permission === 'denied'

  return (
    <Disclosure
      title="Notifications"
      description={
        form.enabled
          ? `Tells you about roles scoring at least ${form.min_score} · ${[form.desktop && 'desktop', form.email && 'email'].filter(Boolean).join(', ') || 'no channels selected'}`
          : 'Disabled — nothing will interrupt you.'
      }
      open={open}
      onToggle={onToggle}
    >
      <div className="space-y-4">
        <Checkbox
          checked={form.enabled}
          onChange={(v) => set({ enabled: v })}
          label="Tell me when a strong match appears"
          hint="Within one scan cycle of it being found."
        />
        <div className={form.enabled ? 'space-y-3' : 'pointer-events-none space-y-3 opacity-50'}>
          <Checkbox
            checked={form.desktop}
            onChange={(v) => set({ desktop: v })}
            label="Desktop notification"
            hint={desktopBlocked
              ? 'Blocked in this browser — allow notifications for this site to use it.'
              : 'While the dashboard is open. Your browser will ask permission once.'}
          />
          <Checkbox
            checked={form.email}
            onChange={(v) => set({ email: v })}
            label="Email"
            hint="Arrives even when nothing is open — uses the same mailbox as replies."
          />
          <Field label="Only for roles scoring at least" hint="0–100.">
            <Input type="number" min={0} max={100} value={form.min_score}
                   onChange={(e) => set({ min_score: e.target.value })} className="w-24" />
          </Field>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <Button variant="primary" busy={busy} onClick={save}>Save</Button>
        {done ? <span className="text-tiny text-ok-400">Saved.</span> : null}
      </div>
    </Disclosure>
  )
}

function ProfileCompleteness({ data, onEdit }) {
  if (!data || data.percent >= 100) return null
  const tone = data.percent >= 75 ? 'ok' : data.percent >= 50 ? 'warn' : 'bad'
  const fill = { ok: 'bg-ok-400', warn: 'bg-warn-400', bad: 'bg-bad-400' }[tone]

  return (
    <div className="material material-edge overflow-hidden rounded-md border border-line px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-n-100">
            Profile is {data.percent}% complete
          </p>
          <p className="mt-0.5 text-tiny text-n-500">
            {data.filled} of {data.total} commonly-required fields filled. What forms ask for most:
          </p>
        </div>
        <button onClick={onEdit} className="press text-tiny font-medium text-blue-500 hover:underline">
          Complete it →
        </button>
      </div>

      <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-n-800">
        <m.div
          className={`h-full rounded-full ${fill}`}
          initial={{ width: 0 }}
          animate={{ width: `${data.percent}%` }}
          transition={springFor()}
        />
      </div>

      {data.missing?.length ? (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {data.missing.map((f) => (
            <span key={f.key}
                  className="rounded-full bg-warn-tint px-2 py-0.5 text-micro font-medium text-warn-400">
              {f.label}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}
