import { useMemo, useState } from 'react'
import { api } from '../lib/api'
import {
  Button,
  Checkbox,
  Disclosure,
  Field,
  Input,
  Note,
  Select,
  Status,
  Switch,
} from './ui'

/*
  Agent configuration: the model, the answers that go into application forms,
  and what to search for. One panel, three groups, collapsed by default.

  It used to be the first thing on the page with every field expanded, which
  put eighteen text inputs above the content the user actually came to see.
*/

const IDENTITY = [
  ['full_name', 'Full name'],
  ['email', 'Email'],
  ['phone', 'Phone'],
  ['location', 'Location'],
  ['linkedin', 'LinkedIn'],
  ['github', 'GitHub'],
  ['portfolio', 'Portfolio'],
  ['current_title', 'Current title'],
  ['current_company', 'Current company'],
  ['years_experience', 'Years of experience'],
  ['highest_degree', 'Highest degree'],
  ['university', 'University'],
  ['work_authorization', 'Work authorisation'],
  ['requires_sponsorship', 'Needs sponsorship'],
  ['notice_period', 'Notice period'],
  ['salary_expectation', 'Salary expectation'],
  ['willing_to_relocate', 'Willing to relocate'],
  ['how_did_you_hear', 'How did you hear about us'],
]

const asList = (v) =>
  Array.isArray(v) ? v : String(v || '').split(',').map((s) => s.trim()).filter(Boolean)
const asText = (v) => (Array.isArray(v) ? v.join(', ') : v || '')

function fmtWhen(iso) {
  if (!iso) return 'soon'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return 'soon'
  if (d.getTime() <= Date.now()) return 'on the next tick'
  return `at ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
}

export default function Settings({ overview, onSaved, open, onToggle }) {
  const [profile, setProfile] = useState(overview.settings.profile)
  const [targeting, setTargeting] = useState(overview.settings.targeting)
  const [limits, setLimits] = useState(overview.settings.limits || {})
  const [schedule, setSchedule] = useState(overview.settings.schedule || {})
  const [provider, setProvider] = useState(overview.llm.provider || 'gemini')
  const [apiKey, setApiKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [test, setTest] = useState(null)
  const [testing, setTesting] = useState(false)

  const missing = useMemo(() => {
    const gaps = []
    if (!overview.llm.available) gaps.push('an AI key')
    if (!profile.full_name) gaps.push('your name')
    if (!profile.email) gaps.push('your email')
    if (!overview.resume?.name) gaps.push('a resume')
    return gaps
  }, [overview, profile])

  async function save() {
    setSaving(true)
    setSaved(false)
    try {
      await api.agentSettings({
        profile,
        targeting: {
          ...targeting,
          titles: asList(targeting.titles),
          exclude_titles: asList(targeting.exclude_titles),
          locations: asList(targeting.locations),
          keywords: asList(targeting.keywords),
          min_fit_score: Number(targeting.min_fit_score) || 55,
          min_years_experience: Number(targeting.min_years_experience ?? 1),
          max_years_experience: Number(targeting.max_years_experience ?? 3),
          allow_internships: !!targeting.allow_internships,
          max_age_days: Number(targeting.max_age_days) || 3,
          require_posted_date: targeting.require_posted_date !== false,
          apply_order: targeting.apply_order || 'recent',
        },
        limits: {
          ...limits,
          retention_days: Math.max(0, Number(limits.retention_days ?? 3) || 0),
          purge_keeps_applied: limits.purge_keeps_applied !== false,
        },
        schedule: {
          ...schedule,
          enabled: !!schedule.enabled,
          discover_every_hours: Math.min(48, Math.max(1, Number(schedule.discover_every_hours ?? 6) || 6)),
          tasks_every_minutes: Math.min(720, Math.max(2, Number(schedule.tasks_every_minutes ?? 30) || 30)),
          quiet_hours: [
            Math.min(23, Math.max(0, Number(schedule.quiet_hours?.[0] ?? 1) || 0)),
            Math.min(24, Math.max(0, Number(schedule.quiet_hours?.[1] ?? 7) || 0)),
          ],
        },
        llm: { provider, ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}) },
      })
      setApiKey('')
      setSaved(true)
      await onSaved()
    } finally {
      setSaving(false)
    }
  }

  const group = 'text-micro font-medium tracking-wide text-n-400 uppercase'

  return (
    <Disclosure
      title="Settings"
      description={
        missing.length ? `Still needed: ${missing.join(', ')}.` : 'Configured and ready.'
      }
      open={open}
      onToggle={onToggle}
      actions={
        missing.length ? (
          <Status tone="warn">{missing.length} to set</Status>
        ) : (
          <Status tone="ok">ready</Status>
        )
      }
    >
      <div className="space-y-6">
        {/* --------------------------------------------------------- model */}
        <div>
          <p className={group}>Model</p>
          <div className="mt-2 grid gap-3 sm:grid-cols-[180px_minmax(0,1fr)_auto] sm:items-end">
            <Field label="Provider">
              <Select value={provider} onChange={(e) => setProvider(e.target.value)}>
                <option value="gemini">Google Gemini</option>
                <option value="groq">Groq</option>
                <option value="openrouter">OpenRouter</option>
                <option value="ollama">Ollama (local)</option>
              </Select>
            </Field>
            <Field
              label="API key"
              hint={
                provider === 'ollama'
                  ? 'Not needed. Run `ollama serve` locally.'
                  : 'Free at aistudio.google.com/apikey. Leave blank to keep the saved key.'
              }
            >
              <Input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={overview.llm.available ? 'saved' : 'paste key'}
                disabled={provider === 'ollama'}
              />
            </Field>
            <Button
              onClick={async () => {
                setTesting(true)
                setTest(null)
                try {
                  setTest(await api.agentLlmTest())
                } finally {
                  setTesting(false)
                }
              }}
              busy={testing}
            >
              Test
            </Button>
          </div>
          {test ? (
            <div className="mt-3">
              <Note tone={test.ok ? 'ok' : 'bad'} onDismiss={() => setTest(null)}>
                {test.ok ? `Connected to ${test.model}.` : test.error}
              </Note>
            </div>
          ) : null}
        </div>

        {/* ------------------------------------------------------ identity */}
        <div>
          <p className={group}>Application answers</p>
          <p className="mt-1 text-tiny leading-relaxed text-n-500">
            These go straight into forms. A blank required field makes the agent record the
            application as failed rather than guess an answer.
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {IDENTITY.map(([key, label]) => (
              <Field key={key} label={label}>
                <Input
                  value={profile[key] || ''}
                  onChange={(e) => setProfile({ ...profile, [key]: e.target.value })}
                />
              </Field>
            ))}
            <Field
              label="Fallback resume"
              hint={`Currently ${overview.resume?.name || 'none found'}. Used only when a job has no tailored resume.`}
            >
              <Input
                value={profile.default_resume || ''}
                onChange={(e) => setProfile({ ...profile, default_resume: e.target.value })}
                placeholder="cv_data/Usairam_Saeed_Resume.pdf"
              />
            </Field>
          </div>
        </div>

        {/* ------------------------------------------------------ targeting */}
        <div>
          <p className={group}>What to go after</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Field label="Wanted titles" hint="Comma separated.">
              <Input
                value={asText(targeting.titles)}
                onChange={(e) => setTargeting({ ...targeting, titles: e.target.value })}
              />
            </Field>
            <Field label="Excluded titles" hint="Any role containing these is dropped.">
              <Input
                value={asText(targeting.exclude_titles)}
                onChange={(e) => setTargeting({ ...targeting, exclude_titles: e.target.value })}
              />
            </Field>
            <Field label="Locations">
              <Input
                value={asText(targeting.locations)}
                onChange={(e) => setTargeting({ ...targeting, locations: e.target.value })}
              />
            </Field>
            <Field label="Skill keywords">
              <Input
                value={asText(targeting.keywords)}
                onChange={(e) => setTargeting({ ...targeting, keywords: e.target.value })}
              />
            </Field>
            <Field label="Minimum fit score" hint="Roles below this are never applied to.">
              <Input
                type="number"
                min={0}
                max={100}
                value={targeting.min_fit_score}
                onChange={(e) => setTargeting({ ...targeting, min_fit_score: e.target.value })}
              />
            </Field>
            <Field label="Max posting age" hint="Days. A week-old posting already has hundreds of applicants.">
              <Input
                type="number"
                min={1}
                max={90}
                value={targeting.max_age_days ?? 3}
                onChange={(e) => setTargeting({ ...targeting, max_age_days: e.target.value })}
              />
            </Field>
            <Field
              label="Experience window"
              hint="Years a posting may demand. A job asking for 8 is dropped before scoring."
            >
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min={0}
                  max={20}
                  value={targeting.min_years_experience ?? 1}
                  onChange={(e) =>
                    setTargeting({ ...targeting, min_years_experience: e.target.value })
                  }
                />
                <span className="shrink-0 text-tiny text-n-500">to</span>
                <Input
                  type="number"
                  min={0}
                  max={20}
                  value={targeting.max_years_experience ?? 3}
                  onChange={(e) =>
                    setTargeting({ ...targeting, max_years_experience: e.target.value })
                  }
                />
              </div>
            </Field>
            <Field label="Apply order" hint="Which roles go first within the age window.">
              <Select
                value={targeting.apply_order || 'recent'}
                onChange={(e) => setTargeting({ ...targeting, apply_order: e.target.value })}
              >
                <option value="recent">Newest first</option>
                <option value="fit">Best fit first</option>
              </Select>
            </Field>
          </div>
          <div className="mt-3 space-y-2.5">
            <Checkbox
              checked={!!targeting.allow_internships}
              onChange={(v) => setTargeting({ ...targeting, allow_internships: v })}
              label="Include internships and placements"
              hint="Off by default: they sit below your experience window."
            />
            <Checkbox
              checked={targeting.require_posted_date !== false}
              onChange={(v) => setTargeting({ ...targeting, require_posted_date: v })}
              label="Skip roles with no posting date"
              hint="Some boards publish no date, so freshness cannot be proven. On means those are never applied to."
            />
          </div>
        </div>

        {/* ---------------------------------------------------- housekeeping */}
        <div>
          <p className={group}>Housekeeping</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Field
              label="Keep jobs for"
              hint="Days. Anything fetched longer ago than this is deleted at the start of the next search, along with its tailored resume."
            >
              <Input
                type="number"
                min={0}
                max={365}
                value={limits.retention_days ?? 3}
                onChange={(e) => setLimits({ ...limits, retention_days: e.target.value })}
              />
            </Field>
          </div>
          <div className="mt-3">
            <Checkbox
              checked={limits.purge_keeps_applied !== false}
              onChange={(v) => setLimits({ ...limits, purge_keeps_applied: v })}
              label="Never delete jobs I applied to"
              hint="On by default. Turning this off removes your own record of where you applied; the double-apply guard still holds either way, because it reads the applications log rather than this table."
            />
          </div>
        </div>

        {/* -------------------------------------------------------- schedule */}
        <div>
          <p className={group}>Schedule</p>
          <p className="mt-1 text-tiny leading-relaxed text-n-500">
            Runs searches and retries on their own, through the same console below. Applying is
            never scheduled — submitting an application always takes your click.
          </p>
          <div className="mt-3">
            <Switch
              checked={!!schedule.enabled}
              onChange={(v) => setSchedule({ ...schedule, enabled: v })}
              label="Run on a schedule"
              hint={
                schedule.enabled && overview.schedule?.nextDiscoverAt
                  ? `Next search ${fmtWhen(overview.schedule.nextDiscoverAt)}; next retry pass ${fmtWhen(overview.schedule.nextTasksAt)}.`
                  : 'Off: everything runs only when you press a button.'
              }
            />
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <Field label="Search every" hint="Hours between discovery runs.">
              <Input
                type="number"
                min={1}
                max={48}
                value={schedule.discover_every_hours ?? 6}
                onChange={(e) => setSchedule({ ...schedule, discover_every_hours: e.target.value })}
              />
            </Field>
            <Field label="Retry queue every" hint="Minutes between passes over failed steps.">
              <Input
                type="number"
                min={2}
                max={720}
                value={schedule.tasks_every_minutes ?? 30}
                onChange={(e) => setSchedule({ ...schedule, tasks_every_minutes: e.target.value })}
              />
            </Field>
            <Field label="Quiet hours" hint="Local time. Nothing fires inside this window.">
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min={0}
                  max={23}
                  value={schedule.quiet_hours?.[0] ?? 1}
                  onChange={(e) =>
                    setSchedule({
                      ...schedule,
                      quiet_hours: [e.target.value, schedule.quiet_hours?.[1] ?? 7],
                    })
                  }
                />
                <span className="shrink-0 text-tiny text-n-500">to</span>
                <Input
                  type="number"
                  min={0}
                  max={24}
                  value={schedule.quiet_hours?.[1] ?? 7}
                  onChange={(e) =>
                    setSchedule({
                      ...schedule,
                      quiet_hours: [schedule.quiet_hours?.[0] ?? 1, e.target.value],
                    })
                  }
                />
              </div>
            </Field>
          </div>
        </div>

        <div className="flex items-center gap-3 border-t border-line pt-4">
          <Button variant="primary" onClick={save} busy={saving}>
            Save settings
          </Button>
          {saved ? <Status tone="ok">saved</Status> : null}
        </div>
      </div>
    </Disclosure>
  )
}
