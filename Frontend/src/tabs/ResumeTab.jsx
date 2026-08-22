import { useCallback, useRef, useState } from 'react'
import { api } from '../lib/api'
import { Segmented } from '../components/apple'
import {
  Button,
  Checkbox,
  Disclosure,
  Field,
  Icon,
  Meter,
  Note,
  PageHead,
  ScoreDisplay,
  Section,
  Select,
  Status,
  Tag,
  Textarea,
} from '../components/ui'

/*
  Resume — one posting in, one tailored resume out.

  Linear: give it a resume and a posting, read what a parser sees, generate.
  The previous version put fifteen panels on the page at once, several of them
  showing the same numbers in different shapes.
*/

const ACCEPT = '.pdf,.docx,.txt,.md'

function prettyBytes(n) {
  if (!n) return '0 B'
  const u = ['B', 'KB', 'MB']
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), 2)
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`
}

export default function ResumeTab({ aiStatus }) {
  const [resumeFile, setResumeFile] = useState(null)
  const [jdText, setJdText] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState(null)
  const [error, setError] = useState('')

  const [useAi, setUseAi] = useState(true)
  const [mode, setMode] = useState('honest')
  const [useLatex, setUseLatex] = useState(true)
  const [contentSource, setContentSource] = useState('profile')
  const [onePage, setOnePage] = useState(false)
  const [reorder, setReorder] = useState(true)
  const [building, setBuilding] = useState(false)
  const [built, setBuilt] = useState(null)
  const [buildError, setBuildError] = useState('')
  const [showParse, setShowParse] = useState(false)
  const [showOptions, setShowOptions] = useState(false)

  const fileRef = useRef(null)
  const canAnalyze = resumeFile && jdText.trim().length >= 60

  const runAnalyze = useCallback(async () => {
    setError('')
    setBuilt(null)
    setBuildError('')
    setAnalyzing(true)
    try {
      setAnalysis(await api.analyze({ resumeFile, jdText }))
    } catch (e) {
      setError(e.message)
      setAnalysis(null)
    } finally {
      setAnalyzing(false)
    }
  }, [resumeFile, jdText])

  const runBuild = useCallback(async () => {
    if (!analysis) return
    setBuildError('')
    setBuilding(true)
    try {
      setBuilt(
        await api.build({
          sessionId: analysis.sessionId,
          reorderBullets: reorder,
          useAi,
          mode: useAi ? mode : 'off',
          useLatex,
          contentSource,
          onePage,
          formats: ['pdf', 'docx', 'txt'],
        }),
      )
    } catch (e) {
      setBuildError(e.message)
    } finally {
      setBuilding(false)
    }
  }, [analysis, reorder, useAi, mode, useLatex, contentSource, onePage])

  return (
    <div className="space-y-4">
      <PageHead
        title="Resume"
        description="Score your resume against one posting, see what a parser actually reads, and generate a tailored version."
      />

      {error ? (
        <Note tone="bad" title="Could not analyze that" onDismiss={() => setError('')}>
          {error}
        </Note>
      ) : null}

      {/* ------------------------------------------------------------ input */}
      <Section title="The posting" description="Your resume, and the job description to aim it at.">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)]">
          <div>
            <p className="mb-1 text-micro font-medium tracking-wide text-n-400 uppercase">Resume</p>
            <button
              onClick={() => fileRef.current?.click()}
              className="press flex w-full items-center gap-3 rounded-sm border border-dashed border-line-strong px-3 py-3 text-left hover:border-n-600 hover:bg-raised"
            >
              <Icon.Doc className="size-4 shrink-0 text-n-500" />
              {resumeFile ? (
                <span className="min-w-0">
                  <span className="block truncate text-sm text-n-200">{resumeFile.name}</span>
                  <span className="text-tiny text-n-500">
                    {prettyBytes(resumeFile.size)} · click to replace
                  </span>
                </span>
              ) : (
                <span>
                  <span className="block text-sm text-n-300">Choose a file</span>
                  <span className="text-tiny text-n-500">PDF, DOCX, TXT or MD</span>
                </span>
              )}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => e.target.files?.[0] && setResumeFile(e.target.files[0])}
            />
          </div>

          <div>
            <p className="mb-1 text-micro font-medium tracking-wide text-n-400 uppercase">
              Job description
            </p>
            <Textarea
              rows={6}
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              placeholder={'Paste the whole posting. The requirements section carries the most weight.'}
            />
            <p className="mt-1 text-tiny text-n-500">
              {jdText.length ? `${jdText.length} characters` : 'At least a few sentences.'}
            </p>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <Button variant="primary" disabled={!canAnalyze} busy={analyzing} onClick={runAnalyze}>
            Analyze
          </Button>
          {!canAnalyze ? (
            <span className="text-tiny text-n-500">
              Add a resume and paste at least a paragraph of the posting.
            </span>
          ) : null}
        </div>
      </Section>

      {analysis ? (
        <>
          <Results analysis={analysis} showParse={showParse} setShowParse={setShowParse} />

          {/* ------------------------------------------------------ generate */}
          <Section
            title="Generate"
            description="Rebuilt from your own content in the house format: single column, standard headings, no tables."
            actions={
              <Button variant="primary" busy={building} onClick={runBuild}>
                {built ? 'Rebuild' : 'Generate'}
              </Button>
            }
          >
            {buildError ? (
              <div className="mb-4">
                <Note tone="bad" title="Build failed" onDismiss={() => setBuildError('')}>
                  {buildError}
                </Note>
              </div>
            ) : null}

            {built ? (
              <div className="mb-4 flex flex-wrap items-end justify-between gap-4 border-b border-line pb-4">
                <div className="flex items-end gap-6">
                  <ScoreDisplay
                    value={built.after.score ?? 0}
                    band={built.after.band}
                    caption={`was ${Math.round(built.before.score)} before`}
                  />
                  {built.latex?.engine && !built.latex?.error ? (
                    <p className="pb-1 text-tiny text-n-500">
                      {built.latex.pages} page · compiled with {built.latex.engine}
                      {built.latex.rewritten ? ` · ${built.latex.rewritten} bullets rewritten` : ''}
                    </p>
                  ) : null}
                </div>
                {/* PDF is the file you actually send, so it is the only
                    primary here. The rest are ordered by how often they get
                    used, not by whatever order the API happened to return. */}
                <div className="flex flex-wrap gap-2">
                  {['pdf', 'docx', 'txt', 'tex']
                    .filter((fmt) => built.downloads[fmt])
                    .map((fmt) => (
                      <a
                        key={fmt}
                        href={built.downloads[fmt]}
                        className={`press inline-flex h-8 items-center gap-1.5 rounded-sm px-3 text-sm ${
                          fmt === 'pdf'
                            ? 'bg-accent font-medium text-n-950 hover:bg-brand-400'
                            : 'border border-line-strong bg-raised text-n-200 hover:bg-n-800'
                        }`}
                      >
                        <Icon.Download />
                        {{ pdf: 'PDF', docx: 'Word', txt: 'Text', tex: 'LaTeX' }[fmt]}
                      </a>
                    ))}
                </div>
              </div>
            ) : null}

            <Disclosure
              title="Options"
              description={`${contentSource === 'profile' ? 'Curated profile' : 'Uploaded file'} · ${useLatex ? 'LaTeX' : 'plain builder'}${useAi ? ' · AI rewrite on' : ''}`}
              open={showOptions}
              onToggle={setShowOptions}
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Content source" hint="profile.yaml is curated and tagged, so it tailors better.">
                  <Select
                    value={contentSource}
                    onChange={(e) => setContentSource(e.target.value)}
                  >
                    <option value="profile">Curated profile</option>
                    <option value="upload">The file I uploaded</option>
                  </Select>
                </Field>
                <div className="space-y-2.5 sm:pt-5">
                  <Checkbox
                    checked={useLatex}
                    onChange={setUseLatex}
                    label="LaTeX"
                    hint="Compiles a real .tex. Falls back to the plain builder with no engine installed."
                  />
                  <Checkbox
                    checked={onePage}
                    onChange={setOnePage}
                    label="Force one page"
                    hint="Off by default: the standard document is two pages with every project on it."
                  />
                  <Checkbox checked={reorder} onChange={setReorder} label="Reorder bullets by relevance" />
                  <Checkbox
                    checked={useAi}
                    onChange={setUseAi}
                    disabled={!aiStatus?.available}
                    label={`AI rewrite${aiStatus?.model ? ` (${aiStatus.model})` : ''}`}
                    hint="Constrained to facts already in your resume. It will not invent metrics."
                  />
                  {useAi ? (
                    <Field
                      label="How far to rewrite"
                      hint="Honest rewords what you already wrote; Aggressive reaches harder for the posting's keywords. Neither may claim a skill your resume does not show."
                    >
                      <Segmented
                        size="sm"
                        ariaLabel="Resume rewrite mode"
                        value={mode}
                        onChange={setMode}
                        options={[
                          { value: 'honest', label: 'Honest' },
                          { value: 'aggressive', label: 'Aggressive' },
                        ]}
                      />
                    </Field>
                  ) : null}
                </div>
              </div>
            </Disclosure>

            {built?.style && !built.style.clean ? (
              <div className="mt-4">
                <Note tone="warn" title="House style check">
                  {built.style.problems.join(' · ')}
                </Note>
              </div>
            ) : null}
          </Section>
        </>
      ) : null}
    </div>
  )
}

/* ----------------------------------------------------------------- results */

function Results({ analysis, showParse, setShowParse }) {
  // `fixes` hangs off `score`, not the response root, and the JD title is
  // under `jd`. Destructuring them from the root gave `undefined.length`,
  // which threw and rendered a blank page where the results should be.
  const { score, match, resume, jd } = analysis
  const fixes = score.fixes || []
  const missing = match.missing.slice(0, 14)

  return (
    <>
      <Section
        title="Score"
        description={jd?.title ? `Against "${jd.title}".` : 'Against this posting.'}
        actions={<ScoreDisplay value={score.total} band={score.band} />}
      >
        <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
          {score.components.map((c) => (
            <Meter key={c.id} label={c.label} value={c.score} max={c.max} detail={c.detail} />
          ))}
        </div>
      </Section>

      {missing.length ? (
        <Section
          title="Missing keywords"
          description="Weighted terms from the posting that your resume never mentions. Only add what you can back up."
        >
          <div className="flex flex-wrap gap-1.5">
            {missing.map((k) => (
              <Tag key={k.term} title={`weight ${k.weight} · ${k.source}`}>
                {k.term}
              </Tag>
            ))}
          </div>
        </Section>
      ) : null}

      {fixes.length ? (
        <Section title="What to fix" description="Ordered by how much each one costs at the filter." flush>
          <ul className="divide-y divide-line">
            {fixes.map((f, i) => (
              <li key={i} className="px-4 py-3">
                <div className="flex items-baseline gap-2">
                  <Status tone={f.priority === 'high' ? 'bad' : f.priority === 'medium' ? 'warn' : 'info'}>
                    {f.priority}
                  </Status>
                  <p className="text-sm text-n-200">{f.title}</p>
                </div>
                <p className="mt-1 text-tiny leading-relaxed text-n-500">{f.detail}</p>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Disclosure
        title="What a parser sees"
        description={`${resume.wordCount} readable words · ${resume.pageCount || '?'} page · .${resume.source}`}
        open={showParse}
        onToggle={setShowParse}
      >
        <dl className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
          {[
            ['Email', resume.contact.email],
            ['Phone', resume.contact.phone],
            ['Location', resume.contact.location],
            ['LinkedIn', resume.contact.linkedin || resume.contact.linkedinHidden],
            ['GitHub', resume.contact.github || resume.contact.githubHidden],
          ].map(([label, value]) => (
            <div key={label} className="flex items-baseline justify-between gap-3 border-b border-line py-1.5">
              <dt className="text-tiny text-n-500">{label}</dt>
              <dd className={`truncate text-tiny ${value ? 'text-n-200' : 'text-bad-400'}`}>
                {value || 'not detected'}
              </dd>
            </div>
          ))}
        </dl>

        {resume.experience.length ? (
          <div className="mt-4">
            <p className="mb-2 text-micro font-medium tracking-wide text-n-400 uppercase">
              Roles reconstructed
            </p>
            <ul className="space-y-1">
              {resume.experience.map((e, i) => (
                <li key={i} className="text-tiny text-n-400">
                  <span className="text-n-200">{e.title || '(no title)'}</span>
                  {e.organization ? ` · ${e.organization}` : ''}
                  <span className={e.period ? '' : 'text-warn-400'}>
                    {' · '}
                    {e.period || 'no dates parsed'}
                  </span>
                  {` · ${e.bullets.length} bullets`}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {resume.layoutWarnings.length ? (
          <div className="mt-4">
            <p className="mb-2 text-micro font-medium tracking-wide text-n-400 uppercase">
              Layout traps
            </p>
            <ul className="space-y-1">
              {resume.layoutWarnings.map((w) => (
                <li key={w.id} className="flex items-baseline gap-2 text-tiny">
                  <Status tone={w.severity === 'low' ? 'info' : 'warn'}>{w.severity}</Status>
                  <span className="text-n-400">{w.title}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Disclosure>
    </>
  )
}
