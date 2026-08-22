import { useCallback, useEffect, useState } from 'react'
import { motion as m } from 'motion/react'
import { springFor } from '../lib/motion'
import { api } from '../lib/api'
import Settings from '../components/Settings'
import Portals from '../components/Portals'
import Mailbox from '../components/Mailbox'
import Credentials from '../components/Credentials'
import {
  Button, Checkbox, Disclosure, Empty, Field, Input, Note, PageHead,
} from '../components/ui'

/*
  Settings — everything that configures the agent, on the screen it belongs on.

  These four panels used to sit collapsed above the jobs table, which put the
  configuration for the whole product in the middle of the one screen people
  open to do work. They are the same panels; they have simply stopped being in
  the way.

  Still an accordion rather than four open forms: one section at a time is the
  only arrangement in which a settings page of this size stays readable.
*/

const SOURCES = [
  { key: 'yc', label: 'Y Combinator' },
  { key: 'hn', label: 'HN "Who is hiring"' },
  { key: 'remote', label: 'Remote & EU boards' },
  { key: 'hidden', label: 'Hidden job market' },
]

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

      <SearchSettings
        overview={overview}
        onSaved={refresh}
        open={panel === 'search'}
        onToggle={(v) => setPanel(v ? 'search' : '')}
      />

      <Portals open={panel === 'portals'} onToggle={(v) => setPanel(v ? 'portals' : '')} />

      <Mailbox open={panel === 'mailbox'} onToggle={(v) => setPanel(v ? 'mailbox' : '')} />

      <Credentials open={panel === 'accounts'} onToggle={(v) => setPanel(v ? 'accounts' : '')} />

      <Settings
        overview={overview}
        onSaved={refresh}
        open={panel === 'agent'}
        onToggle={(v) => setPanel(v ? 'agent' : '')}
      />
    </div>
  )
}

/*
  How ready the profile is to be poured into a form.

  A form-filler wants to know a field is missing before it hits a form that
  needs it, not after. So the gaps are named up front, as a bar and a list of
  exactly which commonly-required fields are still blank — and it steps out of
  the way entirely once the profile is complete, because a green 100% banner is
  just noise.
*/
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

/*
  What a manual search run does.

  These four controls used to be React state on the Jobs screen, which meant
  the button that used them had to be on the same page. They are settings now,
  so "Find new jobs" can live on the dashboard and still know what to do.
*/
function SearchSettings({ overview, onSaved, open, onToggle }) {
  const saved = overview.settings.search || {}
  const targeting = overview.settings.targeting || {}
  const [form, setForm] = useState({
    sources: saved.sources || ['yc', 'hn', 'remote', 'hidden'],
    depth: saved.depth ?? 25,
    scan_ats: saved.scan_ats !== false,
    find_people: saved.find_people !== false,
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  const save = () => {
    setBusy(true)
    setError('')
    api
      .agentSettings({ search: { ...form, depth: Number(form.depth) || 25 } })
      .then(() => { setDone(true); onSaved?.() })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false))
  }

  const count = form.sources.length

  return (
    <Disclosure
      title="Search"
      description={`${count} source${count === 1 ? '' : 's'} · depth ${form.depth} · roles posted in the last ${targeting.max_age_days ?? 3} days, asking ${targeting.min_years_experience ?? 1} to ${targeting.max_years_experience ?? 3} years`}
      open={open}
      onToggle={onToggle}
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="space-y-2.5">
          <p className="text-micro font-medium tracking-wide text-n-400 uppercase">Sources</p>
          {SOURCES.map((s) => (
            <Checkbox
              key={s.key}
              checked={form.sources.includes(s.key)}
              onChange={(on) =>
                setForm((f) => ({
                  ...f,
                  sources: on ? [...f.sources, s.key] : f.sources.filter((k) => k !== s.key),
                }))
              }
              label={s.label}
            />
          ))}
        </div>
        <div className="space-y-3">
          <Field label="Depth" hint="Companies per source, and roles scored.">
            <Input
              type="number"
              min={1}
              max={200}
              value={form.depth}
              onChange={(e) => setForm((f) => ({ ...f, depth: e.target.value }))}
            />
          </Field>
          <Checkbox
            checked={form.scan_ats}
            onChange={(v) => setForm((f) => ({ ...f, scan_ats: v }))}
            label="Scan career portals"
            hint="Detect Greenhouse, Lever and Ashby boards, then pull their live openings."
          />
          <Checkbox
            checked={form.find_people}
            onChange={(v) => setForm((f) => ({ ...f, find_people: v }))}
            label="Find and verify emails"
            hint="Crawl team pages, then MX and SMTP check every address."
          />
        </div>
      </div>

      {error ? (
        <div className="mt-3">
          <Note tone="bad" title="Could not save" onDismiss={() => setError('')}>{error}</Note>
        </div>
      ) : null}

      <div className="mt-4 flex items-center gap-3">
        <Button variant="primary" busy={busy} disabled={!count} onClick={save}>
          Save search settings
        </Button>
        {done && !busy ? <span className="text-tiny text-ok-400">Saved.</span> : null}
        {!count ? <span className="text-tiny text-warn-400">Pick at least one source.</span> : null}
      </div>
    </Disclosure>
  )
}
