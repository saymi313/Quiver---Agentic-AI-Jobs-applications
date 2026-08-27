import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { Segmented } from './apple'
import { Button, Field, Icon, Note, PageHead, Select, Status, Switch } from './ui'

const FONTS = [
  ['times', 'Times New Roman'],
  ['charter', 'Charter'],
  ['palatino', 'Palatino'],
  ['computer_modern', 'Computer Modern'],
]

const SIZES = [10, 10.5, 11, 11.5]

const SECTION_LABELS = {
  summary: 'Summary',
  experience: 'Professional Experience',
  projects: 'Projects',
  skills: 'Technical Skills',
  education: 'Education',
  achievements: 'Achievements & Certifications',
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

export default function ResumeProfilePage({ profileName, onBack }) {
  const [profileData, setProfileData] = useState(null)
  const [opts, setOpts] = useState(DEFAULTS)
  const [url, setUrl] = useState('')
  const [pages, setPages] = useState('')
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState('')
  const [savedNote, setSavedNote] = useState(false)
  const [saving, setSaving] = useState(false)
  const lastUrl = useRef('')

  // Load profile metadata and render options
  useEffect(() => {
    if (!profileName) return
    api
      .agentResumeProfiles()
      .then((data) => {
        const found = (data.rows || []).find((p) => p.name === profileName)
        if (found) {
          setProfileData(found)
          const savedRender = found.render || {}
          setOpts({
            ...DEFAULTS,
            ...savedRender,
            sections: savedRender.sections?.length ? savedRender.sections : DEFAULT_SECTIONS,
          })
        }
      })
      .catch((e) => setError(e.message))
  }, [profileName])

  const set = (patch) => {
    setOpts((o) => ({ ...o, ...patch }))
    setSavedNote(false)
  }

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

  // Rebuild preview with debounce
  const build = useCallback(() => {
    if (!profileName) return
    setBuilding(true)
    setError('')
    api
      .agentResumePreview(profileName, opts)
      .then(({ blob, pages: p }) => {
        const next = URL.createObjectURL(blob)
        if (lastUrl.current) URL.revokeObjectURL(lastUrl.current)
        lastUrl.current = next
        setUrl(next)
        setPages(p)
      })
      .catch((e) => setError(e.message))
      .finally(() => setBuilding(false))
  }, [profileName, opts])

  useEffect(() => {
    const t = setTimeout(build, 400)
    return () => clearTimeout(t)
  }, [build])

  useEffect(() => () => {
    if (lastUrl.current) URL.revokeObjectURL(lastUrl.current)
  }, [])

  const save = () => {
    setSaving(true)
    api
      .agentSaveRender(profileName, opts)
      .then(() => {
        setSavedNote(true)
      })
      .catch((e) => setError(e.message))
      .finally(() => setSaving(false))
  }

  const isDefault = profileData?.isDefault || profileName === 'main'

  return (
    <div className="space-y-6">
      {/* ---------------- Breadcrumbs & Back Navigation ---------------- */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="press inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-medium text-n-200 transition-colors hover:border-n-600 hover:text-n-100"
          >
            <Icon.ArrowLeft className="size-3.5" />
            <span>Back to Profiles</span>
          </button>
          <span className="text-n-600">/</span>
          <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-xs">
            <button
              onClick={onBack}
              className="text-n-400 transition-colors hover:text-n-200"
            >
              Profiles
            </button>
            <span className="text-n-600">/</span>
            <span className="font-semibold text-n-100">{profileName}</span>
          </nav>
        </div>

        <div className="flex items-center gap-2">
          {isDefault ? <Status tone="ok">Default Profile</Status> : null}
          {pages ? <Status tone="neutral">{pages} page{pages === '1' ? '' : 's'}</Status> : null}
        </div>
      </div>

      <PageHead
        title={`Resume Style — ${profileName}`}
        description="Every change instantly recompiles the PDF. Saving applies this typography and layout to all future tailored resumes built for this profile."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="primary" busy={saving} onClick={save}>
              Save to profile
            </Button>
            {url ? (
              <a
                href={url}
                download={`${profileName}-resume.pdf`}
                className="press inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-tiny font-medium text-n-200 transition-colors hover:border-n-600 hover:text-n-100"
              >
                <Icon.Download className="size-3.5" />
                <span>Download PDF</span>
              </a>
            ) : null}
          </div>
        }
      />

      {error ? (
        <Note tone="bad" title="Compilation notice" onDismiss={() => setError('')}>
          {error}
        </Note>
      ) : null}

      {savedNote ? (
        <Note tone="ok" title="Saved successfully" onDismiss={() => setSavedNote(false)}>
          Configuration saved to <code>{profileName}.yaml</code>. Tailored resumes will use these style settings.
        </Note>
      ) : null}

      {/* ---------------- 2-Column Full Page Layout ---------------- */}
      <div className="grid gap-6 lg:grid-cols-[20rem_1fr] items-start">
        {/* Left Column: Style Controls */}
        <div className="space-y-4">
          <div className="rounded-md border border-line bg-surface p-4 space-y-4">
            <p className="text-xs font-semibold text-n-100">Typography & Density</p>

            <Field label="Template Density">
              <Segmented
                ariaLabel="Template density"
                value={opts.template}
                onChange={(v) => set({ template: v })}
                options={[
                  { value: 'standard', label: 'Standard' },
                  { value: 'compact', label: 'Compact' },
                ]}
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Font">
                <Select value={opts.font} onChange={(e) => set({ font: e.target.value })}>
                  {FONTS.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Size">
                <Select
                  value={opts.font_size}
                  onChange={(e) => set({ font_size: Number(e.target.value) })}
                >
                  {SIZES.map((s) => (
                    <option key={s} value={s}>
                      {s} pt
                    </option>
                  ))}
                </Select>
              </Field>
            </div>

            <Field label="Alignment" hint="Ragged-right extracts most cleanly in an ATS.">
              <Segmented
                ariaLabel="Text alignment"
                value={opts.align}
                onChange={(v) => set({ align: v })}
                options={[
                  { value: 'left', label: 'Ragged' },
                  { value: 'justified', label: 'Justified' },
                ]}
              />
            </Field>

            <Switch
              checked={opts.fit_one_page}
              onChange={(v) => set({ fit_one_page: v })}
              label="Fit to one page"
              hint="Trims toward a single page, never below the bullet floors."
            />
          </div>

          <div className="rounded-md border border-line bg-surface p-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-n-100">Section Order</p>
              <span className="text-micro text-n-500">Jake's style ordering</span>
            </div>

            <ul className="divide-y divide-line rounded-md border border-line bg-n-900/40">
              {opts.sections.map((key, i) => (
                <li key={key} className="flex items-center gap-2 px-3 py-2">
                  <span className="flex-1 text-xs font-medium text-n-200">
                    {SECTION_LABELS[key] || key}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => move(key, -1)}
                      disabled={i === 0}
                      aria-label={`Move ${key} up`}
                      className="press rounded p-1 text-n-400 hover:text-n-100 disabled:opacity-30"
                    >
                      <svg
                        viewBox="0 0 24 24"
                        className="size-3.5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                      >
                        <path d="m6 15 6-6 6 6" />
                      </svg>
                    </button>
                    <button
                      onClick={() => move(key, 1)}
                      disabled={i === opts.sections.length - 1}
                      aria-label={`Move ${key} down`}
                      className="press rounded p-1 text-n-400 hover:text-n-100 disabled:opacity-30"
                    >
                      <svg
                        viewBox="0 0 24 24"
                        className="size-3.5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                      >
                        <path d="m6 9 6 6 6-6" />
                      </svg>
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Right Column: High-Res Live PDF Preview */}
        <div className="space-y-3">
          <div className="relative min-h-[640px] overflow-hidden rounded-lg border border-line bg-n-900 shadow-sm">
            {building ? (
              <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-n-950/60 backdrop-blur-xs">
                <div className="size-5 animate-spin rounded-full border-2 border-n-400 border-t-blue-500" />
                <span className="text-xs font-medium text-n-300">Recompiling PDF…</span>
              </div>
            ) : null}

            {url ? (
              <object
                data={url}
                type="application/pdf"
                className="h-[750px] w-full"
                aria-label="Resume live preview"
              >
                <div className="grid h-[600px] place-items-center px-6 text-center text-tiny text-n-500">
                  Inline PDF preview is not supported by your browser viewer. Use the download button above.
                </div>
              </object>
            ) : (
              <div className="grid h-[600px] place-items-center text-tiny text-n-500">
                {building ? 'Building the initial preview…' : 'The compiled preview will appear here.'}
              </div>
            )}
          </div>

          <div className="flex items-center justify-between text-xs text-n-500 px-1">
            <span>ATS Format: Jake Gutierrez Overleaf LaTeX Standard</span>
            {url ? (
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="press inline-flex items-center gap-1.5 text-blue-400 hover:text-blue-300 hover:underline"
              >
                <Icon.Doc className="size-3.5" />
                <span>Open in dedicated browser tab</span>
              </a>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
