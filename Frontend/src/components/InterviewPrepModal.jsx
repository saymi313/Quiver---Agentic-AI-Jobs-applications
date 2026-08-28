import React, { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { Icon } from './ui'

export function InterviewPrepModal({ job, onClose }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!job?.id) return
    setLoading(true)
    setError(null)
    api.agentJobInterviewPrep(job.id)
      .then(res => {
        setData(res)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message || 'Failed to generate interview prep guide.')
        setLoading(false)
      })
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-3xl bg-panel border border-line rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-5 border-b border-line flex items-center justify-between bg-panel-elevated">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-accent bg-accent/10 px-2 py-0.5 rounded-full">
                🧠 1-Page Interview Intelligence
              </span>
              <span className="text-xs text-muted">Job #{job.id}</span>
            </div>
            <h2 className="text-lg font-semibold text-fg mt-1">
              {job.title} <span className="text-muted font-normal">at {job.company_name}</span>
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyCheatSheet}
              disabled={loading || !!error}
              className="btn btn-secondary text-xs flex items-center gap-1.5"
            >
              <Icon name="copy" className="w-3.5 h-3.5" />
              {copied ? '✓ Copied Cheat Sheet!' : 'Copy Cheat Sheet'}
            </button>
            <button
              onClick={onClose}
              className="p-1.5 text-muted hover:text-fg hover:bg-hover rounded-lg transition-colors"
            >
              <Icon name="x" className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {loading ? (
            <div className="py-16 text-center space-y-3">
              <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-sm text-muted">Generating customized technical challenges and STAR response guides...</p>
            </div>
          ) : error ? (
            <div className="p-4 bg-danger/10 border border-danger/20 rounded-xl text-danger text-sm">
              {error}
            </div>
          ) : (
            <>
              {/* Company Context */}
              {guide.company_context && (
                <div className="p-4 bg-panel-elevated border border-line rounded-xl space-y-1.5">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-accent flex items-center gap-1.5">
                    🏢 Company Architecture & Focus
                  </h3>
                  <p className="text-xs text-fg leading-relaxed">
                    {guide.company_context}
                  </p>
                </div>
              )}

              {/* Behavioral (STAR) Questions */}
              {(guide.behavioral_questions || []).length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-fg flex items-center gap-1.5">
                    ⭐ Behavioral STAR Questions & Talking Points
                  </h3>
                  <div className="space-y-2.5">
                    {(guide.behavioral_questions || []).map((q, i) => (
                      <div key={i} className="p-3.5 bg-panel-card border border-line rounded-xl space-y-1.5">
                        <div className="text-xs font-semibold text-fg">
                          {i + 1}. {q.question}
                        </div>
                        <div className="text-xs text-muted pl-3 border-l-2 border-accent">
                          <span className="font-medium text-accent">STAR Tip:</span> {q.star_tip}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Technical / System Design Questions */}
              {(guide.technical_questions || []).length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-fg flex items-center gap-1.5">
                    ⚡ Technical & System Design Challenges
                  </h3>
                  <div className="space-y-2.5">
                    {(guide.technical_questions || []).map((t, i) => (
                      <div key={i} className="p-3.5 bg-panel-card border border-line rounded-xl space-y-1.5">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-semibold text-fg">{i + 1}. {t.question}</span>
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-accent/10 text-accent font-medium">{t.topic}</span>
                        </div>
                        <div className="text-xs text-muted pl-3 border-l-2 border-emerald-400">
                          <span className="font-medium text-emerald-400">Key Architecture Concept:</span> {t.key_concept}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Questions to Ask Interviewer */}
              {(guide.questions_to_ask_interviewer || []).length > 0 && (
                <div className="p-4 bg-panel-elevated border border-line rounded-xl space-y-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-fg flex items-center gap-1.5">
                    🎯 High-Impact Questions to Ask the Interviewer
                  </h3>
                  <ul className="text-xs text-fg space-y-1.5 pl-1">
                    {(guide.questions_to_ask_interviewer || []).map((q, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-accent font-bold mt-0.5">•</span>
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
