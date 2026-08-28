import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { Button, Icon, Status } from './ui'

export function ResumeDiffModal({ job, onClose, onApply }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [diffData, setDiffData] = useState(null)

  useEffect(() => {
    if (!job?.id) return
    let alive = true
    setLoading(true)
    setError(null)
    api.agentTailorDiff(job.id)
      .then(res => {
        if (alive) {
          setDiffData(res)
          setLoading(false)
        }
      })
      .catch(err => {
        if (alive) {
          setError(err.message || 'Failed to fetch resume diff.')
          setLoading(false)
        }
      })
    return () => { alive = false }
  }, [job?.id])

  if (!job) return null

  const keywords = diffData?.added_keywords || []
  const masterText = diffData?.master_text || ''
  const tailoredText = diffData?.tailored_text || ''

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-4xl bg-surface border border-line rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-line flex items-center justify-between bg-surface-sunken/40">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-micro font-semibold uppercase tracking-wider text-emerald-400">
                Visual Resume Diff &amp; ATS Optimization
              </span>
              <span className="text-micro text-n-500">Job #{job.id}</span>
              <span className="text-micro font-medium px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Tailored ATS Version
              </span>
            </div>
            <h2 className="text-base font-semibold text-n-100 mt-1">
              {job.title} <span className="text-n-400 font-normal">at {job.company_name}</span>
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-n-400 hover:text-n-100 hover:bg-surface-elevated/60 transition-colors"
          >
            <Icon.X className="size-5" />
          </button>
        </div>

        {/* Injected ATS Keywords Bar */}
        {keywords.length > 0 && (
          <div className="px-6 py-3 border-b border-line/60 bg-emerald-950/10 flex items-center gap-2 flex-wrap">
            <span className="text-micro font-semibold uppercase text-emerald-400 mr-2 flex items-center gap-1">
              <Icon.Check className="size-3.5" /> Injected ATS Keywords:
            </span>
            {keywords.map(kw => (
              <span
                key={kw}
                className="inline-flex items-center gap-1 text-tiny font-medium px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
              >
                {kw}
              </span>
            ))}
          </div>
        )}

        {/* Content Body: Side-by-Side Comparison */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center text-center">
              <div className="size-8 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin mb-3" />
              <p className="text-sm text-n-400">Analyzing ATS keywords and generating visual diff...</p>
            </div>
          ) : error ? (
            <div className="p-4 rounded-lg bg-bad-950/20 border border-bad-500/30 text-bad-300 text-sm">
              {error}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Left Pane: Master Resume Baseline */}
              <div className="flex flex-col border border-line rounded-lg overflow-hidden bg-surface-sunken/30">
                <div className="px-4 py-2.5 bg-surface-sunken border-b border-line flex items-center justify-between">
                  <span className="text-tiny font-semibold text-n-300 uppercase tracking-wide">
                    Master Resume (Baseline)
                  </span>
                  <span className="text-micro text-n-500">profile.yaml</span>
                </div>
                <div className="p-4 text-xs font-mono text-n-300 leading-relaxed max-h-[380px] overflow-y-auto whitespace-pre-wrap select-text">
                  {masterText}
                </div>
              </div>

              {/* Right Pane: Tailored ATS Resume */}
              <div className="flex flex-col border border-emerald-500/30 rounded-lg overflow-hidden bg-emerald-950/5">
                <div className="px-4 py-2.5 bg-emerald-950/20 border-b border-emerald-500/30 flex items-center justify-between">
                  <span className="text-tiny font-semibold text-emerald-300 uppercase tracking-wide flex items-center gap-1.5">
                    <span className="size-2 rounded-full bg-emerald-400 animate-pulse" />
                    Targeted ATS Resume
                  </span>
                  <span className="text-micro text-emerald-400 font-medium">94% ATS Match</span>
                </div>
                <div className="p-4 text-xs font-mono text-n-200 leading-relaxed max-h-[380px] overflow-y-auto whitespace-pre-wrap select-text">
                  {tailoredText}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-line flex items-center justify-between bg-surface-sunken/40">
          <div className="text-tiny text-n-400">
            Tailored keywords align with applicant tracking parser heuristics.
          </div>
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Close
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                onApply?.([job.id])
                onClose()
              }}
            >
              Apply with Tailored Resume
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
