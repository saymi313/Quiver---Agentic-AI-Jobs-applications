import React, { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { Icon } from './ui'

export function OutreachModal({ job, onClose }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)
  const [activeTab, setActiveTab] = useState('alumni_pitch')
  const [copiedKey, setCopiedKey] = useState(null)

  useEffect(() => {
    if (!job?.id) return
    setLoading(true)
    setError(null)
    api.agentJobOutreach(job.id)
      .then(res => {
        setData(res)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message || 'Failed to generate outreach messages.')
        setLoading(false)
      })
  }, [job?.id])

  if (!job) return null

  const pitches = data?.pitches || {}
  const currentPitch = pitches[activeTab] || {}

  const handleCopy = (text, key) => {
    navigator.clipboard.writeText(text)
    setCopiedKey(key)
    setTimeout(() => setCopiedKey(null), 2000)
  }

  const tabs = [
    { id: 'alumni_pitch', label: '🎓 Alumni Warm Note', desc: 'Anchored on shared university background (FAST-NUCES/NUST)' },
    { id: 'technical_peer', label: '💻 Technical Peer', desc: 'Engineering stack synergy & architectural discussion' },
    { id: 'hiring_manager', label: '👔 Hiring Lead Pitch', desc: 'Direct 80-word value proposition for engineering managers' },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-2xl bg-panel border border-line rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-5 border-b border-line flex items-center justify-between bg-panel-elevated">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-accent bg-accent/10 px-2 py-0.5 rounded-full">
                Referral & Outreach Studio
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
        <div className="p-6 overflow-y-auto flex-1 space-y-5">
          {loading ? (
            <div className="py-16 text-center space-y-3">
              <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-sm text-muted">Crafting high-converting warm outreach variants...</p>
            </div>
          ) : error ? (
            <div className="p-4 bg-danger/10 border border-danger/20 rounded-xl text-danger text-sm">
              {error}
            </div>
          ) : (
            <>
              {/* Tab Selector */}
              <div className="grid grid-cols-3 gap-2 bg-panel-card p-1.5 rounded-xl border border-line">
                {tabs.map(t => (
                  <button
                    key={t.id}
                    onClick={() => setActiveTab(t.id)}
                    className={`py-2 px-3 rounded-lg text-xs font-medium transition-all text-center ${
                      activeTab === t.id
                        ? 'bg-panel-elevated text-fg shadow-sm font-semibold border border-line'
                        : 'text-muted hover:text-fg'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {/* Pitch Preview Box */}
              <div className="bg-panel-elevated border border-line rounded-xl p-4 space-y-4">
                {/* Subject Line */}
                <div>
                  <div className="flex items-center justify-between text-xs text-muted font-medium mb-1">
                    <span>Subject Line</span>
                    <button
                      onClick={() => handleCopy(currentPitch.subject, 'subject')}
                      className="flex items-center gap-1 text-accent hover:underline"
                    >
                      {copiedKey === 'subject' ? '✓ Copied' : 'Copy Subject'}
                    </button>
                  </div>
                  <div className="bg-panel-card border border-line rounded-lg px-3 py-2 text-sm text-fg font-mono select-all">
                    {currentPitch.subject}
                  </div>
                </div>

                {/* Message Body */}
                <div>
                  <div className="flex items-center justify-between text-xs text-muted font-medium mb-1">
                    <span>Message Body</span>
                    <button
                      onClick={() => handleCopy(currentPitch.body, 'body')}
                      className="flex items-center gap-1 text-accent hover:underline"
                    >
                      {copiedKey === 'body' ? '✓ Copied' : 'Copy Message'}
                    </button>
                  </div>
                  <div className="bg-panel-card border border-line rounded-lg p-3.5 text-sm text-fg whitespace-pre-wrap leading-relaxed select-all">
                    {currentPitch.body}
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between pt-2">
                <div className="text-xs text-muted">
                  💡 Tip: Find alumni & engineering leads on LinkedIn search: <br />
                  <span className="font-mono text-[11px] text-fg">"{job.company_name}" AND ("FAST" OR "Engineering")</span>
                </div>
                <div className="flex items-center gap-2">
                  <a
                    href={`mailto:?subject=${encodeURIComponent(currentPitch.subject || '')}&body=${encodeURIComponent(currentPitch.body || '')}`}
                    className="btn btn-secondary text-xs flex items-center gap-1.5"
                  >
                    <Icon name="mail" className="w-3.5 h-3.5" />
                    Open in Email
                  </a>
                  <button
                    onClick={() => handleCopy(`${currentPitch.subject}\n\n${currentPitch.body}`, 'all')}
                    className="btn btn-primary text-xs flex items-center gap-1.5"
                  >
                    <Icon name="copy" className="w-3.5 h-3.5" />
                    {copiedKey === 'all' ? 'Copied Full Note!' : 'Copy Entire Note'}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
