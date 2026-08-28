import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { Button, Icon } from './ui'

export function InterviewPrepModal({ job, onClose }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!job?.id) return
    let alive = true
    setLoading(true)
    setError(null)
    api.agentJobInterviewPrep(job.id)
      .then(res => {
        if (alive) {
          setData(res)
          setLoading(false)
        }
      })
      .catch(err => {
        if (alive) {
          setError(err.message || 'Failed to generate interview prep guide.')
          setLoading(false)
        }
      })
    return () => { alive = false }
  }, [job?.id])

  if (!job) return null

  const guide = data?.guide || {}

  const handleCopyCheatSheet = () => {
    const text = [
      `INTERVIEW PREP CHEATSHEET: ${job.title} at ${job.company_name}`,
      `----------------------------------------------------`,
      `COMPANY CONTEXT:`,
      guide.company_context || '',
      `\nBEHAVIORAL (STAR) QUESTIONS:`,
      ...(guide.behavioral_questions || []).map((q, i) => `${i + 1}. Q: ${q.question}\n   STAR Tip: ${q.star_tip}`),
      `\nTECHNICAL & SYSTEM DESIGN CHALLENGES:`,
      ...(guide.technical_questions || []).map((t, i) => `${i + 1}. [${t.topic}] ${t.question}\n   Key Concept: ${t.key_concept}`),
      `\nQUESTIONS TO ASK THE INTERVIEWER:`,
      ...(guide.questions_to_ask_interviewer || []).map((q, i) => `${i + 1}. ${q}`),
    ].join('\n')

    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-2xl bg-surface border border-line rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-line flex items-center justify-between bg-surface-sunken/40">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-micro font-semibold uppercase tracking-wider text-blue-400">
                Interview Intelligence
              </span>
              <span className="text-micro text-n-500">Job #{job.id}</span>
            </div>
            <h2 className="text-sm font-semibold text-n-100 mt-0.5">
              {job.title} <span className="text-n-400 font-normal">at {job.company_name}</span>
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={loading || !!error}
              onClick={handleCopyCheatSheet}
            >
              <Icon.Copy className="size-3.5" />
              <span>{copied ? 'Copied' : 'Copy Cheatsheet'}</span>
            </Button>
            <button
              type="button"
              onClick={onClose}
              className="press p-1 text-n-400 hover:text-n-100 rounded hover:bg-raised transition-colors"
              title="Close"
            >
              <Icon.X className="size-4" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto flex-1 space-y-5">
          {loading ? (
            <div className="py-16 text-center space-y-2.5">
              <div className="size-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-tiny text-n-400">Generating customized technical and STAR response points...</p>
            </div>
          ) : error ? (
            <div className="p-3.5 bg-bad-950/30 border border-bad-500/30 rounded-lg text-bad-400 text-tiny">
              {error}
            </div>
          ) : (
            <>
              {/* Company Context */}
              {guide.company_context && (
                <div className="p-3.5 bg-raised border border-line rounded-lg space-y-1">
                  <h3 className="text-micro font-semibold uppercase tracking-wider text-blue-400">
                    Company Architecture &amp; Focus
                  </h3>
                  <p className="text-tiny text-n-300 leading-relaxed">
                    {guide.company_context}
                  </p>
                </div>
              )}

              {/* Behavioral (STAR) Questions */}
              {(guide.behavioral_questions || []).length > 0 && (
                <div className="space-y-2.5">
                  <h3 className="text-micro font-semibold uppercase tracking-wider text-n-300">
                    Behavioral STAR Questions
                  </h3>
                  <div className="space-y-2">
                    {(guide.behavioral_questions || []).map((q, i) => (
                      <div key={i} className="p-3 bg-surface-sunken border border-line rounded-lg space-y-1">
                        <div className="text-tiny font-semibold text-n-100">
                          {i + 1}. {q.question}
                        </div>
                        <div className="text-micro text-n-400 pl-2.5 border-l border-blue-500/50">
                          <span className="font-medium text-blue-400">STAR Guide:</span> {q.star_tip}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Technical / System Design Questions */}
              {(guide.technical_questions || []).length > 0 && (
                <div className="space-y-2.5">
                  <h3 className="text-micro font-semibold uppercase tracking-wider text-n-300">
                    Technical &amp; Architecture Challenges
                  </h3>
                  <div className="space-y-2">
                    {(guide.technical_questions || []).map((t, i) => (
                      <div key={i} className="p-3 bg-surface-sunken border border-line rounded-lg space-y-1">
                        <div className="flex items-center justify-between text-tiny">
                          <span className="font-semibold text-n-100">{i + 1}. {t.question}</span>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-raised text-n-400 border border-line">{t.topic}</span>
                        </div>
                        <div className="text-micro text-n-400 pl-2.5 border-l border-ok-500/50">
                          <span className="font-medium text-ok-400">Architecture Concept:</span> {t.key_concept}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Questions to Ask Interviewer */}
              {(guide.questions_to_ask_interviewer || []).length > 0 && (
                <div className="p-3.5 bg-raised border border-line rounded-lg space-y-1.5">
                  <h3 className="text-micro font-semibold uppercase tracking-wider text-n-300">
                    Questions for the Interviewer
                  </h3>
                  <ul className="text-tiny text-n-300 space-y-1 pl-1">
                    {(guide.questions_to_ask_interviewer || []).map((q, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-blue-400 font-bold">•</span>
                        <span>{q}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
