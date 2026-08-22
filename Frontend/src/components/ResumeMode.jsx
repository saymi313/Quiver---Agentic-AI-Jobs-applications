import { useState } from 'react'
import { api } from '../lib/api'
import { Segmented } from './apple'

/*
  How far the resume rewrite may travel, as a control where the work happens.

  Off sends the curated resume unchanged. Honest rewords using only what the
  profile already says. Aggressive rewrites more freely to match the posting's
  keywords. Auto uses the result without stopping to show it first.

  One rule holds across all three modes and is not a setting: the fact gate.
  No mode may put a number, an employer or a technology on the resume that the
  profile does not already carry — so "aggressive" reaches for keyword coverage
  and stronger verbs, never for a claim that is not true. Auto therefore never
  means "may invent"; it only means "do not pause to show me the wording".

  Saving is live and optimistic — the segment moves at once and the setting
  persists behind it, because a control that waits for the network to confirm
  feels dead.
*/

const MODES = [
  { value: 'off', label: 'Off' },
  { value: 'honest', label: 'Honest' },
  { value: 'aggressive', label: 'Aggressive' },
]

export default function ResumeMode({ tailoring, onChanged }) {
  const [mode, setMode] = useState(tailoring?.mode || 'honest')
  const [auto, setAuto] = useState(tailoring?.auto_approve !== false)

  const save = (next) => {
    api.agentSettings({ tailoring: { ...tailoring, ...next } }).then(() => onChanged?.()).catch(() => {})
  }

  const setModeAndSave = (m) => {
    setMode(m)
    save({ mode: m })
  }
  const setAutoAndSave = (v) => {
    setAuto(v)
    save({ auto_approve: v })
  }

  return (
    <label className="flex items-center gap-2.5 text-sm text-n-400">
      <span className="font-medium text-n-300">Resume</span>
      <Segmented
        size="sm"
        ariaLabel="Resume tailoring mode"
        value={mode}
        onChange={setModeAndSave}
        options={MODES}
      />
      <button
        type="button"
        onClick={() => setAutoAndSave(!auto)}
        aria-pressed={auto}
        title={auto
          ? 'Tailored resumes are used without a review step.'
          : 'Each rewritten resume waits for your approval on the Jobs table.'}
        className="press inline-flex items-center gap-1.5"
      >
        <span
          className={`grid size-4 place-items-center rounded-sm border ${
            auto ? 'border-blue-500 bg-blue-500 text-white' : 'border-line-strong text-transparent'
          }`}
        >
          <svg viewBox="0 0 24 24" className="size-3" fill="none" stroke="currentColor"
               strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <path d="m5 12 5 5 9-11" />
          </svg>
        </span>
        <span className={auto ? 'text-n-200' : ''}>Auto</span>
      </button>
    </label>
  )
}
