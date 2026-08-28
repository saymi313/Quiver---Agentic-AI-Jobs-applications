import React, { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { Icon } from './ui'

export function AtsAuditModal({ job, onClose }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)

  useEffect(() => {
    if (!job?.id) return
    setLoading(true)
    setError(null)
    api.agentJobAtsAudit(job.id)
      .then(res => {
        setData(res)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message || 'Failed to compute ATS audit.')
        setLoading(false)
      })
  }, [job?.id])

  if (!job) return null

  const score = data?.score ?? 0
  const scoreColor = score >= 80 ? 'text-emerald-400' : score >= 60 ? 'text-amber-400' : 'text-rose-400'
  const strokeColor = score >= 80 ? '#34d399' : score >= 60 ? '#fbbf24' : '#f87171'

  const matched = (data?.skills_density || []).filter(s => s.status === 'matched')
  const missing = (data?.skills_density || []).filter(s => s.status === 'missing')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-2xl bg-panel border border-line rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-5 border-b border-line flex items-center justify-between bg-panel-elevated">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-accent bg-accent/10 px-2 py-0.5 rounded-full">
                ATS Keyword & Penetration Audit
              </span>
              <span className="text-xs text-muted">Job #{job.id}</span>
            </div>
            <h2 className="text-lg font-semibold text-fg mt-1">
              {job.title} <span className="text-muted font-normal">at {job.company_name}</span>
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-muted hover:text-fg hover:bg-hover rounded-lg transition-colors"
          >
            <Icon name="x" className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {loading ? (
            <div className="py-16 text-center space-y-3">
              <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-sm text-muted">Analyzing resume keyword penetration against job requirements...</p>
            </div>
          ) : error ? (
            <div className="p-4 bg-danger/10 border border-danger/20 rounded-xl text-danger text-sm">
              {error}
            </div>
          ) : (
            <>
              {/* Score Meter & Overview Card */}
              <div className="bg-panel-elevated border border-line rounded-2xl p-5 flex items-center gap-6">
                <div className="relative w-24 h-24 shrink-0 flex items-center justify-center">
                  <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                    <path
                      className="text-line"
                      strokeWidth="3.5"
                      stroke="currentColor"
                      fill="none"
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    />
                    <path
                      strokeDasharray={`${score}, 100`}
                      strokeWidth="3.5"
                      strokeLinecap="round"
                      stroke={strokeColor}
                      fill="none"
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                    <span className={`text-2xl font-bold ${scoreColor}`}>{score}%</span>
                    <span className="text-[10px] uppercase font-semibold text-muted">ATS Fit</span>
                  </div>
                </div>

                <div className="flex-1 space-y-1.5">
                  <h3 className="text-sm font-semibold text-fg">
                    {score >= 80 ? '🔥 High ATS Penetration' : score >= 60 ? '⚡ Moderate Keyword Coverage' : '⚠️ Action Needed'}
                  </h3>
                  <p className="text-xs text-muted leading-relaxed">
                    {data?.fit_reason || `${matched.length} key hard skills present in your tailored resume.`}
                  </p>
                  <div className="flex items-center gap-4 text-xs pt-1">
                    <span className="text-emerald-400 font-medium">✓ {matched.length} Matched</span>
                    <span className="text-rose-400 font-medium">✕ {missing.length} Missing</span>
                    <span className="text-muted">{(data?.action_verbs || []).length} Action Verbs</span>
                  </div>
                </div>
              </div>

              {/* Matched Keywords Grid */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-fg flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    Matched Hard Skills & Keywords ({matched.length})
                  </h4>
                  <span className="text-[11px] text-muted">Found in tailored resume</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {matched.map(s => (
                    <span
                      key={s.term}
                      className="px-2.5 py-1 rounded-lg text-xs font-medium bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 flex items-center gap-1.5"
                    >
                      {s.term}
                      <span className="text-[10px] opacity-75 font-mono">({s.resume_count}x)</span>
                    </span>
                  ))}
                  {matched.length === 0 && (
                    <span className="text-xs text-muted">No explicit keywords matched.</span>
                  )}
                </div>
              </div>

              {/* Missing High Priority Keywords */}
              {missing.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-fg flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-rose-400" />
                      Missing High-Weight ATS Keywords ({missing.length})
                    </h4>
                    <span className="text-[11px] text-muted">Recommended to include</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {missing.map(s => (
                      <span
                        key={s.term}
                        className="px-2.5 py-1 rounded-lg text-xs font-medium bg-rose-500/10 text-rose-300 border border-rose-500/20"
                      >
                        + {s.term}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Action Verbs Found */}
              {(data?.action_verbs || []).length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-fg flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-accent" />
                    Impact & Action Verbs Detected
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {(data?.action_verbs || []).map(v => (
                      <span
                        key={v}
                        className="px-2 py-0.5 rounded-md text-[11px] font-mono bg-panel-card text-muted border border-line"
                      >
                        {v}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Recommendations Box */}
              {(data?.recommendations || []).length > 0 && (
                <div className="p-4 bg-accent/5 border border-accent/15 rounded-xl space-y-2">
                  <h4 className="text-xs font-semibold text-accent flex items-center gap-1.5">
                    <Icon name="sparkles" className="w-3.5 h-3.5" />
                    AI Optimization Checklist
                  </h4>
                  <ul className="text-xs text-fg space-y-1.5 pl-1">
                    {(data.recommendations || []).map((rec, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-accent font-bold mt-0.5">•</span>
                        <span>{rec}</span>
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
