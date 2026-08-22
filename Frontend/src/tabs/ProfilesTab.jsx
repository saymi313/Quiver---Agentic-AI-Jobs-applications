import { useCallback, useEffect, useState } from 'react'
import { motion as m } from 'motion/react'
import { api } from '../lib/api'
import { springFor } from '../lib/motion'
import { CategoryChip } from '../components/apple'
import {
  Button, Empty, Icon, Input, Note, PageHead, Section, Status,
} from '../components/ui'

/*
  Profiles — one resume per kind of role you want.

  A designer applying to design roles and to frontend roles wants two
  different documents, not one that tries to be both. Each profile is a full
  resume source in its own right, and each says which role categories it is
  written for.

  That last part is what makes them worth having. When the agent builds a
  resume for a posting it looks up the profile that claims the posting's
  category and builds from that one — so a UI/UX role gets the design resume
  without anyone remembering to switch first. A category nothing claims falls
  through to the default, which is why there is always exactly one default and
  it cannot be turned off.
*/

const CATEGORIES = [
  ['backend', 'backend'],
  ['frontend', 'frontend'],
  ['fullstack', 'fullstack'],
  ['software_engineer', 'software engineer'],
  ['ai_engineer', 'ai engineer'],
  ['ai_software_engineer', 'ai software engineer'],
  ['product_design', 'product design'],
  ['ui_ux', 'ui ux'],
  ['ui_design', 'ui design'],
  ['ux_design', 'ux design'],
]

export default function ProfilesTab() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [newName, setNewName] = useState('')

  const load = useCallback(
    () => api.agentResumeProfiles().then(setData).catch((e) => setError(e.message)),
    [],
  )
  useEffect(() => { load() }, [load])

  const act = async (key, fn) => {
    setBusy(key)
    setError('')
    try {
      await fn()
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  if (!data) return <Empty title="Loading" />

  const rows = data.rows || []
  // A category is spoken for by the first profile that names it; showing which
  // ones nothing claims is the only way to notice the gap.
  const claimed = new Set(rows.flatMap((r) => r.categories || []))
  const unclaimed = CATEGORIES.filter(([slug]) => !claimed.has(slug))

  return (
    <div className="space-y-4">
      <PageHead
        title="Profiles"
        description="A separate resume for each kind of role you go after. The agent picks the one that matches the posting."
      />

      {error ? (
        <Note tone="bad" title="Could not do that" onDismiss={() => setError('')}>{error}</Note>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-2">
        {rows.map((p, i) => (
          <ProfileCard
            key={p.name}
            profile={p}
            index={i}
            isDefault={p.name === data.default}
            busy={busy}
            onSetDefault={() => act(`default:${p.name}`, () => api.agentSetDefaultProfile(p.name))}
            onDelete={() => act(`delete:${p.name}`, () => api.agentDeleteProfile(p.name))}
            onCategories={(next) =>
              act(`cats:${p.name}`, () => api.agentSetProfileCategories(p.name, next))
            }
          />
        ))}
      </div>

      {unclaimed.length ? (
        <Section
          title="Not covered by any profile"
          description="Roles in these categories build from the default profile."
        >
          <div className="flex flex-wrap gap-1.5">
            {unclaimed.map(([slug]) => <CategoryChip key={slug} slug={slug} />)}
          </div>
        </Section>
      ) : null}

      <Section
        title="New profile"
        description="Starts as a copy of the default, so it compiles from the first minute. Edit the YAML in cv_data/profiles to make it its own."
      >
        <div className="flex flex-wrap items-center gap-2">
          <div className="min-w-[14rem] flex-1">
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && newName.trim() &&
                act('create', () => api.agentCreateProfile(newName.trim(), data.default))
                  .then(() => setNewName(''))}
              placeholder="design"
              aria-label="New profile name"
            />
          </div>
          <Button
            variant="primary"
            busy={busy === 'create'}
            disabled={!newName.trim()}
            onClick={() =>
              act('create', () => api.agentCreateProfile(newName.trim(), data.default))
                .then(() => setNewName(''))
            }
          >
            <Icon.Plus />
            Create
          </Button>
        </div>

        {/* the other way in: read a finished resume back into a profile */}
        <div className="mt-4 border-t border-line pt-4">
          <p className="text-tiny font-medium text-n-200">Or import from a resume</p>
          <p className="mt-0.5 text-micro leading-relaxed text-n-500">
            Upload a PDF or DOCX and Quiver reads it into a new profile —
            {newName.trim() ? ` named “${newName.trim()}”` : ' name it above first'}. A complex
            two-column layout may not carry across perfectly.
          </p>
          <input
            type="file"
            accept=".pdf,.docx"
            disabled={!newName.trim() || busy === 'import'}
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) {
                act('import', () => api.agentImportProfile(newName.trim(), file)).then(() => setNewName(''))
              }
              e.target.value = ''
            }}
            className="mt-2 block w-full text-tiny text-n-400 file:mr-3 file:rounded-full
              file:border-0 file:bg-n-100 file:px-3 file:py-1 file:text-tiny file:font-medium
              file:text-n-950 disabled:opacity-50"
          />
        </div>
      </Section>
    </div>
  )
}

function ProfileCard({ profile, index, isDefault, busy, onSetDefault, onDelete, onCategories }) {
  const [editing, setEditing] = useState(false)
  const chosen = profile.categories || []

  const toggle = (slug) =>
    onCategories(chosen.includes(slug) ? chosen.filter((c) => c !== slug) : [...chosen, slug])

  return (
    <m.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...springFor(), delay: index * 0.04 }}
      className="flex flex-col overflow-hidden rounded-md border border-line bg-surface"
    >
      <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-n-100">{profile.name}</h3>
            {isDefault ? <Status tone="ok">default</Status> : null}
            {profile.error ? <Status tone="bad">unreadable</Status> : null}
          </div>
          <p className="mt-0.5 truncate text-micro text-n-400" title={profile.title}>
            {profile.title || profile.file}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {!isDefault ? (
            <Button size="sm" busy={busy === `default:${profile.name}`} onClick={onSetDefault}>
              Make default
            </Button>
          ) : null}
          {profile.name !== 'main' && !isDefault ? (
            <Button size="sm" variant="ghost" busy={busy === `delete:${profile.name}`}
                    onClick={onDelete}>
              Delete
            </Button>
          ) : null}
        </div>
      </div>

      {profile.summary ? (
        <p className="border-b border-line px-4 py-2.5 text-tiny leading-relaxed text-n-400">
          {profile.summary}
        </p>
      ) : null}

      <dl className="grid grid-cols-3 gap-2 border-b border-line px-4 py-2.5">
        {[['Roles', profile.experience], ['Projects', profile.projects], ['Skills', profile.skills]]
          .map(([label, value]) => (
            <div key={label}>
              <dt className="text-micro tracking-wide text-n-500 uppercase">{label}</dt>
              <dd className="text-sm font-semibold tabular-nums text-n-100">{value ?? 0}</dd>
            </div>
          ))}
      </dl>

      <div className="flex-1 px-4 py-3">
        <div className="flex items-center justify-between gap-2 pb-2">
          <p className="text-micro font-medium tracking-wide text-n-500 uppercase">
            Used for
          </p>
          <button
            onClick={() => setEditing((v) => !v)}
            className="press text-micro text-blue-500 hover:underline"
          >
            {editing ? 'Done' : 'Change'}
          </button>
        </div>

        {editing ? (
          <div className="flex flex-wrap gap-1.5">
            {CATEGORIES.map(([slug]) => {
              const on = chosen.includes(slug)
              return (
                <button
                  key={slug}
                  onClick={() => toggle(slug)}
                  aria-pressed={on}
                  className={`press rounded-full ${
                    on ? 'ring-2 ring-blue-500 ring-offset-1 ring-offset-surface' : 'opacity-45'
                  }`}
                >
                  <CategoryChip slug={slug} />
                </button>
              )
            })}
          </div>
        ) : chosen.length ? (
          <div className="flex flex-wrap gap-1.5">
            {chosen.map((slug) => <CategoryChip key={slug} slug={slug} />)}
          </div>
        ) : (
          <p className="text-tiny text-n-500">
            {isDefault
              ? 'Everything that no other profile claims.'
              : 'Nothing yet — this profile is never picked automatically.'}
          </p>
        )}
      </div>
    </m.article>
  )
}
