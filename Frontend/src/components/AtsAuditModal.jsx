import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { Button, Icon, Status } from './ui'

export function AtsAuditModal({ job, onClose }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)

  useEffect(() => {
    if (!job?.id) return
    let alive = true
    setLoading(true)
    setError(null)
    api.agentJobAtsAudit(job.id)
      .then(res => {
        if (alive) {
          setData(res)
          setLoading(false)
        }
      })
      .catch(err => {
        if (alive) {
          setError(err.message || 'Failed to compute ATS audit.')
          setLoading(false)
        }
      })
    return () => { alive = false }
  }, [job?.id])

  if (!job) return null

  const score = data?.score ?? 0
  const scoreTone = score >= 80 ? 'ok' : score >= 60 ? 'accent' : 'bad'
  const strokeColor = score >= 80 ? '#34d399' : score >= 60 ? '#60a5fa' : '#f87171'

  const matched = (data?.skills_density || []).filter(s => s.status === 'matched')
  const missing = (data?.skills_density || []).filter(s => s.status === 'missing')

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
              <span className="text-micro font-semibold uppercase tracking-wider text-ok-400">
                ATS Keyword &amp; Penetration Audit
              </span>
              <span className="text-micro text-n-500">Job #{job.id}</span>
            </div>
            <h2 className="text-sm font-semibold text-n-100 mt-0.5">
              {job.title} <span className="text-n-400 font-normal">at {job.company_name}</span>
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="press p-1 text-n-400 hover:text-n-100 rounded hover:bg-raised transition-colors"
            title="Close"
          >
            <Icon.X className="size-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto flex-1 space-y-5">
          {loading ? (
            <div className="py-16 text-center space-y-2.5">
              <div className="size-6 border-2 border-ok-500 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-tiny text-n-400">Auditing keyword penetration against job requirements...</p>
            </div>
          ) : error ? (
            <div className="p-3.5 bg-bad-950/30 border border-bad-500/30 rounded-lg text-bad-400 text-tiny">
              {error}
            </div>
          ) : (
            <>
              {/* Score Meter & Overview Card */}
              <div className="bg-raised border border-line rounded-xl p-4 flex items-center gap-5">
                <div className="relative size-20 shrink-0 flex items-center justify-center">
                  <svg className="size-full -rotate-90" viewBox="0 0 36 36">
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
                    <span className="text-xl font-bold text-n-100 tabular-nums">{score}%</span>
                    <span className="text-[9px] uppercase font-semibold text-n-500">ATS Fit</span>
                  </div>
                </div>

                <div className="flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <Status tone={scoreTone}>
                      {score >= 80 ? 'High ATS Fit' : score >= 60 ? 'Moderate Fit' : 'Low Keyword Match'}
                    </Status>
                  </div>
                  <p className="text-tiny text-n-300 leading-relaxed">
                    {data?.fit_reason || `${matched.length} key hard skills verified in your tailored resume.`}
                  </p>
                  <div className="flex items-center gap-3 text-micro pt-1">
                    <span className="text-ok-400 font-medium">{matched.length} Matched</span>
                    <span className="text-bad-400 font-medium">{missing.length} Missing</span>
                    <span className="text-n-500">{(data?.action_verbs || []).length} Action Verbs</span>
                  </div>
                </div>
              </div>

              {/* Matched Keywords Grid */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-micro font-semibold uppercase tracking-wider text-n-300">
                    Matched Skills &amp; Keywords ({matched.length})
                  </h4>
                  <span className="text-micro text-n-500">Present in resume</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {matched.map(s => (
                    <span
                      key={s.term}
                      className="px-2 py-0.5 rounded text-micro font-medium bg-ok-950/40 text-ok-300 border border-ok-500/30 flex items-center gap-1"
                    >
                      <span>{s.term}</span>
                      <span className="text-[10px] opacity-75 font-mono">({s.resume_count}x)</span>
                    </span>
                  ))}
                  {matched.length === 0 && (
                    <span className="text-tiny text-n-500">No explicit keywords matched.</span>
                  )}
                </div>
              </div>

              {/* Missing High Priority Keywords */}
              {missing.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-micro font-semibold uppercase tracking-wider text-n-300">
                      Missing Target Keywords ({missing.length})
                    </h4>
                    <span className="text-micro text-n-500">Suggested additions</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {missing.map(s => (
                      <span
                        key={s.term}
                        className="px-2 py-0.5 rounded text-micro font-medium bg-bad-950/40 text-bad-300 border border-bad-500/30"
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
                  <h4 className="text-micro font-semibold uppercase tracking-wider text-n-300">
                    Active Verbs Detected
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {(data?.action_verbs || []).map(v => (
                      <span
                        key={v}
                        className="px-2 py-0.5 rounded text-micro font-mono bg-surface-sunken text-n-400 border border-line"
                      >
                        {v}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Recommendations Box */}
              {(data?.recommendations || []).length > 0 && (
                <div className="p-3.5 bg-surface-sunken border border-line rounded-lg space-y-1.5">
                  <h4 className="text-micro font-semibold uppercase tracking-wider text-blue-400">
                    ATS Recommendations
                  </h4>
                  <ul className="text-tiny text-n-300 space-y-1 pl-1">
                    {(data.recommendations || []).map((rec, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-blue-400 font-bold">•</span>
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
