import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { Button, Icon, Status } from './ui'

export function OutreachModal({ job, onClose }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)
  const [activeTab, setActiveTab] = useState('alumni_pitch')
  const [copiedKey, setCopiedKey] = useState(null)

  useEffect(() => {
    if (!job?.id) return
    let alive = true
    setLoading(true)
    setError(null)
    api.agentJobOutreach(job.id)
      .then(res => {
        if (alive) {
          setData(res)
          setLoading(false)
        }
      })
      .catch(err => {
        if (alive) {
          setError(err.message || 'Failed to generate outreach notes.')
          setLoading(false)
        }
      })
    return () => { alive = false }
  }, [job?.id])

  if (!job) return null

  const pitches = data?.pitches || {}
  const currentPitch = pitches[activeTab] || pitches['alumni'] || {}

  const handleCopy = (text, key) => {
    if (!text) return
    navigator.clipboard.writeText(text)
    setCopiedKey(key)
    setTimeout(() => setCopiedKey(null), 2000)
  }

  const tabs = [
    { id: 'alumni_pitch', label: 'Alumni Network', desc: 'Shared university connection' },
    { id: 'technical_peer', label: 'Technical Peer', desc: 'Engineering stack discussion' },
    { id: 'hiring_manager', label: 'Hiring Lead', desc: 'Direct concise candidate pitch' },
  ]

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
                Referral &amp; Outreach Notes
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

        {/* Body */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4">
          {loading ? (
            <div className="py-16 text-center space-y-2.5">
              <div className="size-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-tiny text-n-400">Preparing customized outreach notes...</p>
            </div>
          ) : error ? (
            <div className="p-3.5 bg-bad-950/30 border border-bad-500/30 rounded-lg text-bad-400 text-tiny">
              {error}
            </div>
          ) : (
            <>
              {/* Tab Selector */}
              <div className="grid grid-cols-3 gap-1.5 bg-surface-sunken p-1 rounded-lg border border-line">
                {tabs.map(t => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setActiveTab(t.id)}
                    className={`py-1.5 px-2.5 rounded text-tiny font-medium transition-all text-center ${
                      activeTab === t.id
                        ? 'bg-raised text-n-100 shadow-2xs font-semibold border border-line'
                        : 'text-n-400 hover:text-n-200'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {/* Pitch Preview Box */}
              <div className="bg-raised border border-line rounded-lg p-4 space-y-3.5">
                {/* Subject Line */}
                <div>
                  <div className="flex items-center justify-between text-micro text-n-500 font-medium mb-1">
                    <span>Subject</span>
                    <button
                      type="button"
                      onClick={() => handleCopy(currentPitch.subject, 'subject')}
                      className="press inline-flex items-center gap-1 text-blue-400 hover:underline"
                    >
                      {copiedKey === 'subject' ? 'Copied' : 'Copy Subject'}
                    </button>
                  </div>
                  <div className="bg-surface-sunken border border-line rounded px-3 py-2 text-tiny text-n-200 font-mono select-all">
                    {currentPitch.subject || '—'}
                  </div>
                </div>

                {/* Message Body */}
                <div>
                  <div className="flex items-center justify-between text-micro text-n-500 font-medium mb-1">
                    <span>Message Body</span>
                    <button
                      type="button"
                      onClick={() => handleCopy(currentPitch.body, 'body')}
                      className="press inline-flex items-center gap-1 text-blue-400 hover:underline"
                    >
                      {copiedKey === 'body' ? 'Copied' : 'Copy Body'}
                    </button>
                  </div>
                  <div className="bg-surface-sunken border border-line rounded p-3 text-tiny text-n-200 whitespace-pre-wrap leading-relaxed select-all">
                    {currentPitch.body || '—'}
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between pt-1 border-t border-line">
                <p className="text-micro text-n-500">
                  Search query on LinkedIn: <code className="text-n-300">"{job.company_name}" Engineering</code>
                </p>
                <div className="flex items-center gap-2">
                  <a
                    href={`mailto:?subject=${encodeURIComponent(currentPitch.subject || '')}&body=${encodeURIComponent(currentPitch.body || '')}`}
                    className="press inline-flex items-center gap-1.5 rounded border border-line bg-surface px-3 py-1.5 text-tiny font-medium text-n-200 hover:border-n-600"
                  >
                    <Icon.Mail className="size-3.5" />
                    <span>Open Email</span>
                  </a>
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => handleCopy(`${currentPitch.subject}\n\n${currentPitch.body}`, 'all')}
                  >
                    <Icon.Copy className="size-3.5" />
                    <span>{copiedKey === 'all' ? 'Copied Note' : 'Copy All'}</span>
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
