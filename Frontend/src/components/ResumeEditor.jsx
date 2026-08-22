import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { Sheet, Segmented } from './apple'
import { Button, Field, Icon, Note, Select, Switch } from './ui'

/*
  The resume, adjustable in the browser.

  Tsenta lets you pick a template, a font, a size, an alignment and a one-page
  fit, and reorder the sections; this is the same, wired to the LaTeX builder
  that already produces the real documents. Every change rebuilds the PDF on the
  right, so the control and its result sit side by side — you are editing the
  thing itself, not a description of it.

  What the controls cannot do is break the document: the options round-trip
  through the same validator the builder uses, so an out-of-range value is
  pulled back to the nearest valid one rather than producing a resume that will
  not compile. Saving writes the style into the profile, so the tailored resumes
  a real application sends look like the one approved here.
*/

const FONTS = [
  ['times', 'Times'],
  ['charter', 'Charter'],
  ['palatino', 'Palatino'],
]
const SIZES = [10, 10.5, 11, 11.5]
const SECTION_LABELS = {
  summary: 'Summary',
  experience: 'Experience',
  projects: 'Projects',
  skills: 'Skills',
  education: 'Education',
  achievements: 'Achievements',
}
const DEFAULT_SECTIONS = ['summary', 'experience', 'projects', 'skills', 'education', 'achievements']

const DEFAULTS = {
  template: 'standard',
  font: 'times',
  font_size: 10.5,
  align: 'left',
  fit_one_page: false,
  sections: DEFAULT_SECTIONS,
}

export default function ResumeEditor({ profile, initial, open, onClose, onSaved }) {
  const [opts, setOpts] = useState(DEFAULTS)
  const [url, setUrl] = useState('')
  const [pages, setPages] = useState('')
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState('')
  const [savedNote, setSavedNote] = useState(false)
  const lastUrl = useRef('')

  // Seed from the profile's saved style each time the editor opens.
  useEffect(() => {
    if (open) {
      setOpts({ ...DEFAULTS, ...(initial || {}),
                sections: (initial?.sections?.length ? initial.sections : DEFAULT_SECTIONS) })
      setError('')
      setSavedNote(false)
    }
  }, [open, initial])

  const set = (patch) => { setOpts((o) => ({ ...o, ...patch })); setSavedNote(false) }

  const move = (key, dir) => {
    setOpts((o) => {
      const arr = [...o.sections]
      const i = arr.indexOf(key)
      const j = i + dir
      if (i < 0 || j < 0 || j >= arr.length) return o
      ;[arr[i], arr[j]] = [arr[j], arr[i]]
      return { ...o, sections: arr }
    })
    setSavedNote(false)
  }

  // Rebuild the preview whenever the options change, debounced so dragging a
  // control does not fire a compile per keystroke.
  const build = useCallback(() => {
    if (!open || !profile) return
    setBuilding(true)
    setError('')
    api
      .agentResumePreview(profile, opts)
      .then(({ blob, pages: p }) => {
        const next = URL.createObjectURL(blob)
        if (lastUrl.current) URL.revokeObjectURL(lastUrl.current)
        lastUrl.current = next
        setUrl(next)
        setPages(p)
      })
      .catch((e) => setError(e.message))
      .finally(() => setBuilding(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, profile, opts])

  useEffect(() => {
    if (!open) return
    const t = setTimeout(build, 500)
    return () => clearTimeout(t)
  }, [open, build])

  useEffect(() => () => { if (lastUrl.current) URL.revokeObjectURL(lastUrl.current) }, [])

  const save = () => {
    api.agentSaveRender(profile, opts).then(() => {
      setSavedNote(true)
      onSaved?.()
    }).catch((e) => setError(e.message))
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      wide
      title={`Resume style — ${profile}`}
      description="Every change rebuilds the PDF. Saving applies the style to this profile's tailored resumes too."
      footer={
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={save}>Save to profile</Button>
          <a
            href={url || undefined}
            download={`${profile}-resume.pdf`}
            className={`press inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-tiny
              font-medium ${url ? 'text-n-300 ring-1 ring-line hover:text-n-100'
                : 'pointer-events-none text-n-500 ring-1 ring-line opacity-50'}`}
          >
            <Icon.Download />
            Download PDF
          </a>
          {savedNote ? <span className="text-tiny text-ok-400">Saved to the profile.</span> : null}
          {pages ? <span className="ml-auto text-micro text-n-500">{pages} page{pages === '1' ? '' : 's'}</span> : null}
        </div>
      }
    >
      <div className="grid gap-5 lg:grid-cols-[18rem_1fr]">
        {/* controls */}
        <div className="space-y-4">
          {error ? (
            <Note tone="bad" title="Could not build" onDismiss={() => setError('')}>{error}</Note>
          ) : null}

          <Field label="Template">
            <Segmented
              ariaLabel="Template density"
              value={opts.template}
              onChange={(v) => set({ template: v })}
              options={[{ value: 'standard', label: 'Standard' }, { value: 'compact', label: 'Compact' }]}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Font">
              <Select value={opts.font} onChange={(e) => set({ font: e.target.value })}>
                {FONTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </Field>
            <Field label="Size">
              <Select value={opts.font_size} onChange={(e) => set({ font_size: Number(e.target.value) })}>
                {SIZES.map((s) => <option key={s} value={s}>{s} pt</option>)}
              </Select>
            </Field>
          </div>

          <Field label="Alignment" hint="Ragged-right extracts most cleanly in an ATS.">
            <Segmented
              ariaLabel="Text alignment"
              value={opts.align}
              onChange={(v) => set({ align: v })}
              options={[{ value: 'left', label: 'Ragged' }, { value: 'justified', label: 'Justified' }]}
            />
          </Field>

          <Switch
            checked={opts.fit_one_page}
            onChange={(v) => set({ fit_one_page: v })}
            label="Fit to one page"
            hint="Trims toward a single page, never below the bullet floors."
          />

          <div>
            <p className="pb-1.5 text-micro font-medium tracking-wide text-n-500 uppercase">
              Section order
            </p>
            <ul className="divide-y divide-line rounded-md border border-line">
              {opts.sections.map((key, i) => (
                <li key={key} className="flex items-center gap-2 px-3 py-1.5">
                  <span className="flex-1 text-sm text-n-200">{SECTION_LABELS[key] || key}</span>
                  <button onClick={() => move(key, -1)} disabled={i === 0}
                          aria-label={`Move ${key} up`}
                          className="press rounded p-1 text-n-500 hover:text-n-100 disabled:opacity-30">
                    <svg viewBox="0 0 24 24" className="size-3.5" fill="none" stroke="currentColor"
                         strokeWidth="1.8" strokeLinecap="round"><path d="m6 15 6-6 6 6" /></svg>
                  </button>
                  <button onClick={() => move(key, 1)} disabled={i === opts.sections.length - 1}
                          aria-label={`Move ${key} down`}
                          className="press rounded p-1 text-n-500 hover:text-n-100 disabled:opacity-30">
                    <svg viewBox="0 0 24 24" className="size-3.5" fill="none" stroke="currentColor"
                         strokeWidth="1.8" strokeLinecap="round"><path d="m6 9 6 6 6-6" /></svg>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* live preview */}
        <div>
          <div className="relative min-h-[24rem] overflow-hidden rounded-md border border-line bg-n-850">
            {building ? (
              <div className="absolute inset-0 z-10 grid place-items-center bg-n-950/40">
                <span className="text-tiny text-n-500">Building…</span>
              </div>
            ) : null}
            {url ? (
              // An <object> renders a blob PDF more reliably than an <iframe>,
              // and the plain blob URL is used with no `#toolbar` fragment —
              // Chrome refuses to render a blob-URL PDF once a fragment is
              // attached, which left this pane blank. The fallback below covers
              // any browser that still will not embed a PDF at all.
              <object data={url} type="application/pdf"
                      className="h-[32rem] w-full lg:h-[36rem]" aria-label="Resume preview">
                <div className="grid h-[32rem] place-items-center px-6 text-center text-tiny text-n-500">
                  Your browser will not preview the PDF inline. Open it in a new tab or download it
                  from the buttons below.
                </div>
              </object>
            ) : (
              <div className="grid h-[32rem] place-items-center text-tiny text-n-500">
                {building ? 'Building the first preview…' : 'The preview appears here.'}
              </div>
            )}
          </div>
          {url ? (
            <a href={url} target="_blank" rel="noreferrer"
               className="press mt-2 inline-flex items-center gap-1.5 text-tiny text-blue-500 hover:underline">
              <Icon.Doc className="size-3.5" />
              Open preview in a new tab
            </a>
          ) : null}
        </div>
      </div>
    </Sheet>
  )
}
