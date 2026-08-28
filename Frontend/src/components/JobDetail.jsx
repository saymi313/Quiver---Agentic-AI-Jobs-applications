import { useState } from 'react'
import { api } from '../lib/api'
import { CategoryChip, ScoreRing, SidePanel } from './apple'
import { Button, Icon, Status } from './ui'
import { OutreachModal } from './OutreachModal'
import { AtsAuditModal } from './AtsAuditModal'
import { InterviewPrepModal } from './InterviewPrepModal'
import { ResumeDiffModal } from './ResumeDiffModal'

/*
  One role, opened out.

  The table answers "what is there". This answers "is this one worth my time",
  which needs the things a row has no room for: the salary, the level, where it
  is worked, when it closes, and the skills the posting actually named — the
  list a tailored resume is aimed at. So the posting stops being a link and
  becomes the parsed document it always was.

  Three actions live at the foot, in the order a decision is made: pass on it,
  keep it for later, or apply. Apply is the one filled button; the other two are
  quieter, because most roles are not the one.
*/

const CURRENCY_SYMBOL = { USD: '$', GBP: '£', EUR: '€', JPY: '¥', INR: '₹' }

function money(n, currency) {
  if (n == null) return null
  const sym = CURRENCY_SYMBOL[currency] || ''
  const k = n >= 1000 ? `${Math.round(n / 1000)}k` : `${Math.round(n)}`
  return `${sym}${k}`
}

function formatSalary(job) {
  const { salary_min: lo, salary_max: hi, salary_currency: cur } = job
  if (lo == null && hi == null) return null
  const code = cur && !CURRENCY_SYMBOL[cur] ? `${cur} ` : ''
  if (lo != null && hi != null) return `${code}${money(lo, cur)} – ${money(hi, cur)} /yr`
  return `${code}${money(lo ?? hi, cur)} /yr`
}

const AR_LABEL = { remote: 'Remote', hybrid: 'Hybrid', onsite: 'On-site' }

/*
  Some boards store the description as HTML. Rendering it raw shows the tags;
  rendering it as HTML would trust a third party's markup on our page. So it is
  reduced to text: tags dropped, block elements turned into line breaks, the
  handful of entities that actually appear decoded, and runs of blank lines
  collapsed. The DOM does the parsing, so it handles malformed markup the way a
  browser would rather than the way a regex would.
*/
function plainText(raw) {
  if (!raw) return ''
  if (!/[<&]/.test(raw)) return raw.trim()
  const doc = new DOMParser().parseFromString(
    raw.replace(/<\/(p|div|li|h[1-6]|br)>/gi, '\n').replace(/<br\s*\/?>/gi, '\n'),
    'text/html',
  )
  return (doc.body.textContent || '')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]+\n/g, '\n')
    .trim()
}

function Fact({ icon: I, label, children }) {
  if (!children) return null
  return (
    <div className="flex items-center gap-2.5">
      <I className="size-4 shrink-0 text-n-400" />
      <div className="min-w-0">
        <p className="text-micro tracking-wide text-n-500 uppercase">{label}</p>
        <p className="truncate text-sm text-n-100">{children}</p>
      </div>
    </div>
  )
}

function when(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const days = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days}d ago`
  return d.toLocaleDateString()
}

function deadlineWhen(iso) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const days = Math.round((d.getTime() - Date.now()) / 86400000)
  const date = d.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })
  if (days < 0) return `${date} (closed)`
  if (days === 0) return `${date} (today)`
  if (days <= 14) return `${date} (${days}d left)`
  return date
}

export default function JobDetail({
  job,
  busy,
  onClose,
  onApply,
  onGenerate,
  onReview,
  onSave,
  onPass,
  onOpenOutreach,
  onOpenAtsAudit,
  onOpenInterviewPrep,
}) {
  const [outreachOpen, setOutreachOpen] = useState(false)
  const [atsAuditOpen, setAtsAuditOpen] = useState(false)
  const [interviewPrepOpen, setInterviewPrepOpen] = useState(false)
  const [diffOpen, setDiffOpen] = useState(false)

  if (!job) return null

  const salary = formatSalary(job)
  const skills = job.skills || []
  const blocked = ['applied', 'skipped', 'duplicate'].includes(job.status)

  return (
    <>
      <SidePanel
        open={!!job}
        onClose={onClose}
        title={job.title}
        subtitle={job.company_name || undefined}
        badge={
          <div className="flex flex-wrap items-center gap-2">
            <CategoryChip slug={job.role_category} />
            {job.source ? <span className="text-micro text-n-500">{job.source}</span> : null}
            {job.deadline ? (
              <Status tone="warn" dot={false}>
                closes {deadlineWhen(job.deadline)}
              </Status>
            ) : null}
          </div>
        }
        footer={
          <div className="flex flex-wrap items-center gap-2">
            {!blocked ? (
              <Button variant="primary" disabled={busy} onClick={() => onApply?.([job.id])}>
                Apply
              </Button>
            ) : (
              <Status tone={job.status === 'applied' ? 'ok' : 'neutral'}>{job.status}</Status>
            )}
            <Button variant="ghost" disabled={busy} onClick={() => onSave?.(job)}>
              <Icon.Bookmark filled={job.saved} className="size-3.5" />
              {job.saved ? 'Saved' : 'Save'}
            </Button>
            {!blocked ? (
              <Button variant="ghost" disabled={busy} onClick={() => onPass?.(job)}>
                Pass
              </Button>
            ) : null}
            <a
              href={job.url}
              target="_blank"
              rel="noreferrer"
              className="press ml-auto inline-flex items-center gap-1.5 text-tiny text-blue-500 hover:underline"
            >
              <Icon.Doc className="size-3.5" />
              Original posting
            </a>
          </div>
        }
      >
        <div className="space-y-5">
          {/* the score, large, because it is the first question */}
          {job.fit_score ? (
            <div className="flex items-center gap-3">
              <ScoreRing value={job.fit_score} size={52} stroke={4} />
              <p className="text-tiny leading-relaxed text-n-500">{job.fit_reason}</p>
            </div>
          ) : null}

          {/* Action Toolbar for AI & Outreach Intelligence */}
          <div className="flex flex-wrap items-center gap-2 p-1.5 rounded-lg bg-surface-sunken border border-line">
            <button
              type="button"
              onClick={() => {
                if (onOpenOutreach) onOpenOutreach(job)
                else setOutreachOpen(true)
              }}
              className="press flex-1 min-w-[100px] py-1.5 px-2 rounded-md bg-surface border border-line hover:border-n-600 text-tiny font-medium text-blue-400 flex items-center justify-center gap-1.5 transition-colors"
            >
              <Icon.Send className="size-3.5" />
              <span>Outreach</span>
            </button>
            <button
              type="button"
              onClick={() => {
                if (onOpenAtsAudit) onOpenAtsAudit(job)
                else setAtsAuditOpen(true)
              }}
              className="press flex-1 min-w-[100px] py-1.5 px-2 rounded-md bg-surface border border-line hover:border-n-600 text-tiny font-medium text-ok-400 flex items-center justify-center gap-1.5 transition-colors"
            >
              <Icon.Check className="size-3.5" />
              <span>ATS Audit</span>
            </button>
            <button
              type="button"
              onClick={() => {
                if (onOpenInterviewPrep) onOpenInterviewPrep(job)
                else setInterviewPrepOpen(true)
              }}
              className="press flex-1 min-w-[100px] py-1.5 px-2 rounded-md bg-surface border border-line hover:border-n-600 text-tiny font-medium text-purple-400 flex items-center justify-center gap-1.5 transition-colors"
            >
              <Icon.Sparkles className="size-3.5" />
              <span>Interview Prep</span>
            </button>
          </div>

          {/* the facts a row cannot hold */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-3.5 border-y border-line py-4">
            <Fact icon={Icon.Pin} label="Location">
              {job.location || (job.remote ? 'Remote' : null)}
            </Fact>
            <Fact icon={Icon.Calendar} label="Posted">
              {when(job.posted_at || job.discovered_at)}
            </Fact>
            <Fact icon={Icon.Coin} label="Salary">{salary}</Fact>
            <Fact icon={Icon.Steps} label="Level">
              {job.seniority ? job.seniority[0].toUpperCase() + job.seniority.slice(1) : null}
            </Fact>
            <Fact icon={Icon.Home} label="Arrangement">
              {AR_LABEL[job.work_arrangement]}
            </Fact>
            <Fact icon={Icon.Clock} label="Type">{job.employment_type}</Fact>
            {job.deadline ? (
              <Fact icon={Icon.Calendar} label="Closes">{deadlineWhen(job.deadline)}</Fact>
            ) : null}
          </div>

          {/* the skills the posting named — what a tailored resume is aimed at */}
          {skills.length ? (
            <div>
              <p className="pb-2 text-micro font-medium tracking-wide text-n-500 uppercase">
                Skills &amp; technologies
              </p>
              <div className="flex flex-wrap gap-1.5">
                {skills.map((s) => (
                  <span
                    key={s}
                    className="rounded-full bg-hue-violet px-2.5 py-1 text-micro font-medium text-hue-violet-fg"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {/* the resume for this role, if one is built */}
          {job.has_resume ? (
            <div className="flex items-center gap-2 rounded-md border border-line bg-raised px-3 py-2">
              <Icon.File className="size-4 text-n-400" />
              <span className="flex-1 text-tiny text-n-300">Tailored resume ready</span>
              <a
                href={api.agentResumeUrl(job.id, 'pdf')}
                target="_blank"
                rel="noreferrer"
                className="press text-tiny text-blue-500 hover:underline"
              >
                view
              </a>
              <button
                onClick={() => setDiffOpen(true)}
                className="press text-tiny text-emerald-400 font-medium hover:underline flex items-center gap-1"
                title="Visual Resume Diff & ATS Analysis"
              >
                diff
              </button>
              {job.resume_approved === 0 ? (
                <button onClick={() => onReview?.(job.id)} className="press text-tiny text-warn-400">
                  review
                </button>
              ) : null}
            </div>
          ) : !blocked ? (
            <Button size="sm" disabled={busy} onClick={() => onGenerate?.([job.id])}>
              Generate a tailored resume
            </Button>
          ) : null}

          {/* the description, last, for when the parsed facts are not enough */}
          {job.description ? (
            <div>
              <p className="pb-2 text-micro font-medium tracking-wide text-n-500 uppercase">
                Description
              </p>
              <p className="text-tiny leading-relaxed whitespace-pre-line text-n-300">
                {plainText(job.description).slice(0, 4000)}
                {plainText(job.description).length > 4000 ? '…' : ''}
              </p>
            </div>
          ) : null}
        </div>
      </SidePanel>

      {/* Intelligence Modals */}
      {outreachOpen && (
        <OutreachModal job={job} onClose={() => setOutreachOpen(false)} />
      )}
      {atsAuditOpen && (
        <AtsAuditModal job={job} onClose={() => setAtsAuditOpen(false)} />
      )}
      {interviewPrepOpen && (
        <InterviewPrepModal job={job} onClose={() => setInterviewPrepOpen(false)} />
      )}
      {diffOpen && (
        <ResumeDiffModal job={job} onClose={() => setDiffOpen(false)} onApply={(ids) => onApply?.(ids)} />
      )}
    </>
  )
}
