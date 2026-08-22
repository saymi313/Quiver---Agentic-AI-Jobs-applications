import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Button, Disclosure, Field, Input, Note, Status } from './ui'

/*
  Saved answers — the questions a profile cannot hold.

  Some forms ask things no structured field will ever carry: "Are you open to
  co-living?", "What's your favourite project?". The agent will not invent an
  answer, so it stops and waits. This is where you answer such a question once;
  from then on the agent reuses it wherever a form asks the same thing.

  The match is on the question's wording, not an exact string — "open to
  co-living" answers "Are you open to co-living arrangements?" — because it is
  your own words being reused, never a guess.
*/

export default function SavedAnswers({ overview, onSaved, open, onToggle }) {
  const [rows, setRows] = useState(() => overview.settings.custom_answers || [])
  const [draft, setDraft] = useState({ match: '', answer: '' })
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  // Keep in step if the overview is refreshed by another panel.
  useEffect(() => {
    setRows(overview.settings.custom_answers || [])
  }, [overview])

  const persist = (next) => {
    setRows(next)
    setBusy(true)
    setDone(false)
    api.agentSettings({ custom_answers: next })
      .then(() => { setDone(true); onSaved?.() })
      .catch(() => {})
      .finally(() => setBusy(false))
  }

  const add = () => {
    if (!draft.match.trim() || !draft.answer.trim()) return
    persist([...rows, { match: draft.match.trim(), answer: draft.answer.trim() }])
    setDraft({ match: '', answer: '' })
  }

  const remove = (i) => persist(rows.filter((_, idx) => idx !== i))

  const summary = rows.length
    ? `${rows.length} saved answer${rows.length === 1 ? '' : 's'}`
    : 'Answer an unusual question once; the agent reuses it on every form that asks.'

  return (
    <Disclosure
      title="Saved answers"
      description={summary}
      open={open}
      onToggle={onToggle}
      actions={done ? <Status tone="ok" dot={false}>saved</Status> : null}
    >
      <Note tone="info" title="How these are used">
        These fill only where the profile had no truthful answer — a work
        authorisation or salary question is still answered from your profile.
        Matching is on the question's wording, so it need not be word-for-word.
      </Note>

      {rows.length ? (
        <ul className="mt-4 divide-y divide-line rounded-md border border-line">
          {rows.map((r, i) => (
            <li key={i} className="flex items-start gap-3 px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-n-100">{r.match}</p>
                <p className="mt-0.5 whitespace-pre-wrap text-micro leading-relaxed text-n-400">
                  {r.answer}
                </p>
              </div>
              <button
                onClick={() => remove(i)}
                disabled={busy}
                className="press shrink-0 text-tiny text-n-500 hover:text-bad-400"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {/* add one */}
      <div className="mt-4 grid gap-3">
        <Field label="When a question asks about…" hint="a few words from the question, e.g. “open to co-living”">
          <Input
            value={draft.match}
            onChange={(e) => setDraft((d) => ({ ...d, match: e.target.value }))}
            placeholder="open to co-living"
          />
        </Field>
        <Field label="…answer with" hint="what to put in the field — “Yes”, “No”, or a sentence">
          <textarea
            value={draft.answer}
            onChange={(e) => setDraft((d) => ({ ...d, answer: e.target.value }))}
            placeholder="Yes"
            rows={2}
            className="w-full rounded-md border border-line bg-base px-3 py-2 text-sm text-n-100 outline-none placeholder:text-n-600 focus:border-blue-500"
          />
        </Field>
        <div>
          <Button
            size="sm"
            variant="primary"
            busy={busy}
            disabled={!draft.match.trim() || !draft.answer.trim()}
            onClick={add}
          >
            Add answer
          </Button>
        </div>
      </div>
    </Disclosure>
  )
}
