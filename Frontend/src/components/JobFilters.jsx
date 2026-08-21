import { useMemo } from 'react'
import { AnimatePresence, motion as m } from 'motion/react'
import { springFor } from '../lib/motion'
import { Button, Icon, Input, Select } from './ui'
import { CategoryChip, Segmented } from './apple'

/*
  The filter bar.

  Two rows, and the second one is optional. The first carries what is asked for
  on almost every visit — which stage, what words, what order — and the second
  holds everything else behind a single button that says how many of them are
  on. A dozen controls laid out at once would read as a settings screen rather
  than a way to narrow a list.

  Two rules shape the rest:

    * Every active filter appears as a chip that removes itself when clicked.
      A filter you cannot see is a filter you forget you set, and then the list
      looks broken rather than filtered.
    * Categories are picked by clicking their own colour rather than from a
      dropdown. The chips already carry a hue everywhere else in the app, so
      the filter and the row it matches look like the same thing.
*/

const STATUS_FILTERS = [
  ['not_applied', 'Ready'],
  ['applied', 'Applied'],
  ['failed', 'Failed'],
  ['skipped', 'Filtered out'],
  ['', 'All'],
]

const SORTS = [
  ['recent', 'Newest first'],
  ['score', 'Best match first'],
  ['company', 'By company'],
  ['title', 'By role'],
]

const AGES = [
  ['', 'Any time'],
  ['1', 'Last 24 hours'],
  ['3', 'Last 3 days'],
  ['7', 'Last week'],
  ['30', 'Last month'],
]

const SCORES = [
  ['', 'Any match'],
  ['40', '40 and above'],
  ['55', '55 and above'],
  ['70', '70 and above'],
  ['85', '85 and above'],
]

const PLACES = [
  ['', 'Anywhere'],
  ['remote', 'Remote only'],
  ['onsite', 'On-site only'],
]

const RESUMES = [
  ['', 'With or without'],
  ['yes', 'Resume ready'],
  ['no', 'No resume yet'],
]

/** The empty filter set. Anything equal to this is "no filter", which is what
 *  the chip row and the count both key off. */
export const NO_FILTERS = {
  status: 'not_applied',
  categories: [],
  sources: [],
  q: '',
  company: '',
  location: '',
  minScore: '',
  age: '',
  place: '',
  resume: '',
  sort: 'recent',
}

/** Turn the UI's filter state into the query the API takes. */
export function toQuery(f, limit = 400) {
  const out = { limit }
  if (f.status) out.status = f.status
  if (f.categories.length) out.category = f.categories.join(',')
  if (f.sources.length) out.source = f.sources.join(',')
  if (f.q) out.q = f.q
  if (f.company) out.company = f.company
  if (f.location) out.location = f.location
  if (f.minScore) out.min_score = f.minScore
  if (f.age) out.posted_within_days = f.age
  if (f.place) out.remote = f.place === 'remote'
  if (f.resume) out.has_resume = f.resume === 'yes'
  if (f.sort && f.sort !== 'recent') out.sort = f.sort
  return out
}

/* Which filters are "extra" — the ones behind the button, and so the ones the
   count on it refers to. Status and sort are always visible, so neither counts:
   a badge that reads "1" before you have touched anything is noise. */
function extras(f) {
  const on = []
  if (f.categories.length) on.push(['categories', `${f.categories.length} categories`])
  if (f.sources.length) on.push(['sources', f.sources.join(', ')])
  if (f.company) on.push(['company', `company: ${f.company}`])
  if (f.location) on.push(['location', `in: ${f.location}`])
  if (f.minScore) on.push(['minScore', `match ${f.minScore}+`])
  if (f.age) on.push(['age', AGES.find(([v]) => v === f.age)?.[1] || ''])
  if (f.place) on.push(['place', PLACES.find(([v]) => v === f.place)?.[1] || ''])
  if (f.resume) on.push(['resume', RESUMES.find(([v]) => v === f.resume)?.[1] || ''])
  if (f.q) on.push(['q', `“${f.q}”`])
  return on
}

export default function JobFilters({
  value,
  onChange,
  categories = [],
  sources = [],
  open,
  onToggleOpen,
  matched,
  total,
  search,
  onSearch,
}) {
  const set = (patch) => onChange({ ...value, ...patch })
  const active = useMemo(() => extras(value), [value])

  const toggleIn = (key, item) => {
    const list = value[key]
    set({ [key]: list.includes(item) ? list.filter((x) => x !== item) : [...list, item] })
  }

  const clearOne = (key) =>
    set({ [key]: Array.isArray(value[key]) ? [] : '' })

  return (
    <div className="border-b border-line">
      {/* ------------------------------------------------------ always on */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-2.5">
        <Segmented
          size="sm"
          ariaLabel="Filter by application status"
          value={value.status}
          onChange={(v) => set({ status: v })}
          options={STATUS_FILTERS.map(([v, label]) => ({ value: v, label }))}
        />

        <div className="min-w-[9rem] flex-1">
          <Input
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder="Search roles and descriptions"
            aria-label="Search tracked jobs"
            className="h-8 py-0"
          />
        </div>

        <div className="w-40">
          <Select
            value={value.sort}
            onChange={(e) => set({ sort: e.target.value })}
            aria-label="Sort order"
            className="h-8 py-0"
          >
            {SORTS.map(([v, label]) => (
              <option key={v} value={v}>{label}</option>
            ))}
          </Select>
        </div>

        <Button size="sm" variant={open ? 'default' : 'ghost'} onClick={() => onToggleOpen(!open)}>
          <Icon.Sliders />
          Filters
          {active.length ? (
            <span className="ml-1 rounded-full bg-blue-500 px-1.5 text-micro font-semibold text-white">
              {active.length}
            </span>
          ) : null}
        </Button>
      </div>

      {/* ------------------------------------------------------- the rest */}
      <AnimatePresence initial={false}>
        {open ? (
          <m.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={springFor()}
            className="overflow-hidden border-t border-line bg-raised"
          >
            <div className="space-y-4 px-4 py-3.5">
              <div>
                <p className="pb-2 text-micro font-medium tracking-wide text-n-500 uppercase">
                  Role category
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {categories.map((c) => {
                    const on = value.categories.includes(c.slug)
                    return (
                      <button
                        key={c.slug}
                        onClick={() => toggleIn('categories', c.slug)}
                        aria-pressed={on}
                        className={`press rounded-full ${
                          on ? 'ring-2 ring-blue-500 ring-offset-1 ring-offset-raised' : ''
                        }`}
                      >
                        <CategoryChip slug={c.slug} />
                        <span className="sr-only">{on ? 'selected' : 'not selected'}</span>
                      </button>
                    )
                  })}
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Labelled label="Posted">
                  <Select value={value.age} onChange={(e) => set({ age: e.target.value })}
                          aria-label="Posted within" className="h-8 py-0">
                    {AGES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </Select>
                </Labelled>

                <Labelled label="Match score">
                  <Select value={value.minScore} onChange={(e) => set({ minScore: e.target.value })}
                          aria-label="Minimum match score" className="h-8 py-0">
                    {SCORES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </Select>
                </Labelled>

                <Labelled label="Location">
                  <Select value={value.place} onChange={(e) => set({ place: e.target.value })}
                          aria-label="Remote or on-site" className="h-8 py-0">
                    {PLACES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </Select>
                </Labelled>

                <Labelled label="Tailored resume">
                  <Select value={value.resume} onChange={(e) => set({ resume: e.target.value })}
                          aria-label="Whether a resume is built" className="h-8 py-0">
                    {RESUMES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </Select>
                </Labelled>

                <Labelled label="Company">
                  <Input value={value.company} onChange={(e) => set({ company: e.target.value })}
                         placeholder="Any company" aria-label="Company name contains"
                         className="h-8 py-0" />
                </Labelled>

                <Labelled label="Place name">
                  <Input value={value.location} onChange={(e) => set({ location: e.target.value })}
                         placeholder="Berlin, NY, Pakistan…" aria-label="Location contains"
                         className="h-8 py-0" />
                </Labelled>

                <Labelled label="Portal" className="sm:col-span-2">
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {sources.map(([name, count]) => {
                      const on = value.sources.includes(name)
                      return (
                        <button
                          key={name}
                          onClick={() => toggleIn('sources', name)}
                          aria-pressed={on}
                          className={`press rounded-full px-2.5 py-1 text-micro font-medium ${
                            on
                              ? 'bg-n-100 text-n-950'
                              : 'bg-surface text-n-400 ring-1 ring-line hover:text-n-100'
                          }`}
                        >
                          {name}
                          <span className="ml-1 opacity-60 tabular-nums">{count}</span>
                        </button>
                      )
                    })}
                  </div>
                </Labelled>
              </div>
            </div>
          </m.div>
        ) : null}
      </AnimatePresence>

      {/* --------------------------------------------- what is on, and how many */}
      {active.length ? (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-line px-4 py-2">
          <span className="text-micro tracking-wide text-n-500 uppercase">Filtering by</span>
          {active.map(([key, label]) => (
            <button
              key={key}
              onClick={() => clearOne(key)}
              className="press inline-flex items-center gap-1 rounded-full bg-n-850 px-2 py-0.5
                text-micro text-n-300 hover:bg-n-800 hover:text-n-100"
              title={`Remove this filter`}
            >
              {label}
              <Icon.X className="size-2.5" />
            </button>
          ))}
          <button
            onClick={() => onChange({ ...NO_FILTERS, status: value.status, sort: value.sort })}
            className="press ml-1 text-micro text-blue-500 hover:underline"
          >
            Clear all
          </button>
          {matched != null ? (
            <span className="ml-auto text-micro tabular-nums text-n-500">
              {matched} of {total}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function Labelled({ label, children, className = '' }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 block text-micro font-medium tracking-wide text-n-500 uppercase">
        {label}
      </span>
      {children}
    </label>
  )
}
