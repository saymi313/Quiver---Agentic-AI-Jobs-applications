import { useCallback, useEffect, useRef, useState } from 'react'
import { motion as m, AnimatePresence } from 'motion/react'
import { api } from '../lib/api'
import { Segmented } from './apple'
import { springFor } from '../lib/motion'
import { Button, Field, Icon, Input, Note, PageHead, Select, Status, Switch } from './ui'

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
  const [activeView, setActiveView] = useState('split') // 'split' | 'content' | 'style'
  const [profileData, setProfileData] = useState(null)
  const [rawYamlData, setRawYamlData] = useState(null)
  const [opts, setOpts] = useState(DEFAULTS)
  const [url, setUrl] = useState('')
  const [pages, setPages] = useState('')
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState('')
  const [savedNote, setSavedNote] = useState(false)
  const [saving, setSaving] = useState(false)
  const [isDirty, setIsDirty] = useState(false)
  const lastUrl = useRef('')
  const snapshotRef = useRef(null)

  // Form State
  const [candidate, setCandidate] = useState({
    name: '',
    title: '',
    email: '',
    phone: '',
    location: '',
    summary: '',
    links: [],
  })
  const [experience, setExperience] = useState([])
  const [projects, setProjects] = useState([])
  const [skills, setSkills] = useState([])
  const [education, setEducation] = useState([])
  const [awards, setAwards] = useState([])
  const [certifications, setCertifications] = useState([])

  // Load Profile Metadata and Structured Data
  const loadData = useCallback(() => {
    if (!profileName) return
    setError('')
    Promise.all([
      api.agentResumeProfiles().catch(() => ({ rows: [] })),
      api.agentGetProfileData(profileName).catch(() => null),
    ])
      .then(([profilesRes, dataRes]) => {
        const found = (profilesRes?.rows || []).find((p) => p.name === profileName)
        if (found) {
          setProfileData(found)
          const savedRender = found.render || {}
          const newOpts = {
            ...DEFAULTS,
            ...savedRender,
            sections: savedRender.sections?.length ? savedRender.sections : DEFAULT_SECTIONS,
          }
          setOpts(newOpts)
        }

        const d = (dataRes?.ok && dataRes.data) || found?.data
        if (d) {
          setRawYamlData(d)
          const cand = d.candidate || {}
          const candState = {
            name: cand.name || '',
            title: cand.title || '',
            email: cand.email || '',
            phone: cand.phone || '',
            location: cand.location || '',
            summary: (cand.summary || '').trim(),
            links: cand.links || [],
          }
          const expState = (d.experience || []).map((e) => ({
            company: e.company || '',
            role: e.role || '',
            period: e.period || '',
            location: e.location || '',
            bullets: (e.bullets || []).map((b) => (typeof b === 'string' ? { text: b } : { text: b?.text || '' })),
          }))
          const projState = (d.projects || []).map((p) => ({
            name: p.name || '',
            tech: p.tech || '',
            period: p.period || '',
            bullets: (p.bullets || []).map((b) => (typeof b === 'string' ? { text: b } : { text: b?.text || '' })),
          }))
          const skillsState = (d.skills || []).map((s) => ({
            line: typeof s === 'string' ? s : (s?.line || ''),
          }))
          const eduState = (d.education || []).map((edu) => ({
            institution: edu.institution || '',
            location: edu.location || '',
            degree: edu.degree || '',
            period: edu.period || '',
            courses: edu.courses || '',
          }))
          const awardsState = d.awards || []
          const certsState = d.certifications || []

          setCandidate(candState)
          setExperience(expState)
          setProjects(projState)
          setSkills(skillsState)
          setEducation(eduState)
          setAwards(awardsState)
          setCertifications(certsState)

          // Save baseline snapshot for Cancel / Reset
          snapshotRef.current = {
            candidate: candState,
            experience: expState,
            projects: projState,
            skills: skillsState,
            education: eduState,
            awards: awardsState,
            certifications: certsState,
            opts: found?.render || DEFAULTS,
          }
          setIsDirty(false)
        }
      })
      .catch((e) => setError(e.message))
  }, [profileName])

  useEffect(() => {
    loadData()
  }, [loadData])

  const setStyleOption = (patch) => {
    setOpts((o) => ({ ...o, ...patch }))
    setSavedNote(false)
    setIsDirty(true)
  }

  const moveSection = (key, dir) => {
    setOpts((o) => {
      const arr = [...o.sections]
      const i = arr.indexOf(key)
      const j = i + dir
      if (i < 0 || j < 0 || j >= arr.length) return o
      ;[arr[i], arr[j]] = [arr[j], arr[i]]
      return { ...o, sections: arr }
    })
    setSavedNote(false)
    setIsDirty(true)
  }

  // Rebuild preview with debounce
  const buildPreview = useCallback(() => {
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
    const t = setTimeout(buildPreview, 400)
    return () => clearTimeout(t)
  }, [buildPreview])

  useEffect(() => () => {
    if (lastUrl.current) URL.revokeObjectURL(lastUrl.current)
  }, [])

  // Cancel / Revert to last loaded snapshot
  const handleCancel = () => {
    if (!snapshotRef.current) return
    const s = snapshotRef.current
    setCandidate(JSON.parse(JSON.stringify(s.candidate)))
    setExperience(JSON.parse(JSON.stringify(s.experience)))
    setProjects(JSON.parse(JSON.stringify(s.projects)))
    setSkills(JSON.parse(JSON.stringify(s.skills)))
    setEducation(JSON.parse(JSON.stringify(s.education)))
    setAwards(JSON.parse(JSON.stringify(s.awards)))
    setCertifications(JSON.parse(JSON.stringify(s.certifications)))
    setOpts({
      ...DEFAULTS,
      ...s.opts,
      sections: s.opts?.sections?.length ? s.opts.sections : DEFAULT_SECTIONS,
    })
    setIsDirty(false)
    setSavedNote(false)
    setError('')
  }

  // Save Style and Content Data
  const handleSaveAll = async () => {
    setSaving(true)
    setError('')
    setSavedNote(false)
    try {
      // 1. Save style options
      await api.agentSaveRender(profileName, opts)

      // 2. Prepare structured data payload
      const updatedData = {
        ...(rawYamlData || {}),
        candidate: {
          name: candidate.name,
          title: candidate.title,
          email: candidate.email,
          phone: candidate.phone,
          location: candidate.location,
          links: candidate.links,
          summary: candidate.summary,
        },
        experience: experience.map((e) => ({
          ...e,
          bullets: (e.bullets || []).filter((b) => (b.text || '').trim()),
        })),
        projects: projects.map((p) => ({
          ...p,
          bullets: (p.bullets || []).filter((b) => (b.text || '').trim()),
        })),
        skills: skills.filter((s) => (s.line || '').trim()),
        education: education,
        awards: awards,
        certifications: certifications,
        render: opts,
      }

      await api.agentSaveProfileData(profileName, updatedData)

      // Update baseline snapshot
      snapshotRef.current = {
        candidate: JSON.parse(JSON.stringify(candidate)),
        experience: JSON.parse(JSON.stringify(experience)),
        projects: JSON.parse(JSON.stringify(projects)),
        skills: JSON.parse(JSON.stringify(skills)),
        education: JSON.parse(JSON.stringify(education)),
        awards: JSON.parse(JSON.stringify(awards)),
        certifications: JSON.parse(JSON.stringify(certifications)),
        opts: JSON.parse(JSON.stringify(opts)),
      }

      setIsDirty(false)
      setSavedNote(true)
      buildPreview()
    } catch (e) {
      setError(e.message || 'Could not save profile.')
    } finally {
      setSaving(false)
    }
  }

  // Helper Form Handlers
  const handleAddExperience = () => {
    setExperience((prev) => [
      {
        id: `exp_${Date.now()}`,
        company: 'Acme Technologies',
        role: 'Senior Software Engineer',
        period: '2024 to Present',
        location: 'Remote',
        bullets: [{ text: 'Architected high-throughput services and microservices.' }],
      },
      ...prev,
    ])
    setIsDirty(true)
  }

  const handleAddProject = () => {
    setProjects((prev) => [
      {
        id: `proj_${Date.now()}`,
        name: 'Distributed Cloud Storage',
        tech: 'React, Node.js, TypeScript, Docker',
        period: '2025',
        bullets: [{ text: 'Built real-time syncing workflows and responsive web clients.' }],
      },
      ...prev,
    ])
    setIsDirty(true)
  }

  const handleAddEducation = () => {
    setEducation((prev) => [
      {
        institution: 'University of Engineering and Technology',
        location: 'Islamabad, Pakistan',
        degree: 'Bachelor of Science in Software Engineering',
        period: '2022 to 2026',
        courses: 'Algorithms, Data Structures, Operating Systems, Distributed Systems',
      },
      ...prev,
    ])
    setIsDirty(true)
  }

  const isDefault = profileData?.isDefault || profileName === 'main'

  return (
    <div className="space-y-6">
      {/* ---------------- Breadcrumbs & Back Navigation ---------------- */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="press inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-medium text-n-200 transition-all hover:border-n-600 hover:text-n-100 active:scale-[0.98]"
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

        {/* Apple Segmented View Toggle */}
        <div className="flex items-center gap-3">
          <Segmented
            size="sm"
            ariaLabel="Editor mode switcher"
            value={activeView}
            onChange={setActiveView}
            options={[
              { value: 'split', label: 'Split View' },
              { value: 'content', label: 'Content & Data' },
              { value: 'style', label: 'Typography & Style' },
          {pages ? <Status tone="neutral">{pages} page{pages === '1' ? '' : 's'}</Status> : null}
        </div>
      </div>

      <PageHead
        title={`Resume Profile — ${profileName}`}
        description="Edit structured candidate data, adjust typography, and compile publication-grade ATS resumes in real time."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              disabled={!isDirty || saving}
              onClick={handleCancel}
            >
              Cancel
            </Button>
            <Button variant="primary" busy={saving} onClick={handleSaveAll}>
              Update Profile
            </Button>
            {url ? (
              <a
                href={url}
                download={`${profileName}-resume.pdf`}
                className="press inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-tiny font-medium text-n-200 transition-all hover:border-n-600 hover:text-n-100 active:scale-[0.98]"
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
          Profile <code>{profileName}.yaml</code> updated and recompiled with zero errors.
        </Note>
      ) : null}

      {/* ---------------- View Modes ---------------- */}
      <div
        className={`grid gap-6 items-start ${
          activeView === 'split'
            ? 'lg:grid-cols-[1.1fr_0.9fr]'
            : activeView === 'content'
            ? 'grid-cols-1'
            : 'lg:grid-cols-[22rem_1fr]'
        }`}
      >
        {/* Left / Center: Form & Style Controls */}
        <div className="space-y-5">
          {/* CONTENT EDITOR */}
          {(activeView === 'split' || activeView === 'content') && (
            <m.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={springFor()}
              className="space-y-4"
            >
              {/* 1. Candidate Info Card */}
              <div className="rounded-lg border border-line bg-surface p-5 space-y-4 shadow-2xs">
                <div className="flex items-center justify-between border-b border-line pb-3">
                  <p className="text-xs font-semibold tracking-wide text-n-100 uppercase">
                    1. Candidate Information
                  </p>
                  <span className="text-micro text-n-500">Contact & Header Bar</span>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Full Name">
                    <Input
                      value={candidate.name}
                      onChange={(e) => {
                        setCandidate((c) => ({ ...c, name: e.target.value }))
                        setIsDirty(true)
                      }}
                      placeholder="e.g. Alex Morgan"
                    />
                  </Field>
                  <Field label="Target Headline / Title">
                    <Input
                      value={candidate.title}
                      onChange={(e) => {
                        setCandidate((c) => ({ ...c, title: e.target.value }))
                        setIsDirty(true)
                      }}
                      placeholder="e.g. Senior Full Stack Engineer"
                    />
                  </Field>
                  <Field label="Email Address">
                    <Input
                      value={candidate.email}
                      onChange={(e) => {
                        setCandidate((c) => ({ ...c, email: e.target.value }))
                        setIsDirty(true)
                      }}
                      placeholder="e.g. alex.morgan@example.com"
                    />
                  </Field>
                  <Field label="Phone Number">
                    <Input
                      value={candidate.phone}
                      onChange={(e) => {
                        setCandidate((c) => ({ ...c, phone: e.target.value }))
                        setIsDirty(true)
                      }}
                      placeholder="e.g. +1 (555) 019-2834"
                    />
                  </Field>
                  <Field label="Location">
                    <Input
                      value={candidate.location}
                      onChange={(e) => {
                        setCandidate((c) => ({ ...c, location: e.target.value }))
                        setIsDirty(true)
                      }}
                      placeholder="e.g. San Francisco, CA (or Remote)"
                    />
                  </Field>
                </div>

                <Field
                  label="Executive Summary"
                  hint="Keep between 2-4 lines. Focus on quantifiable achievements, core stack, and years of experience."
                >
                  <textarea
                    rows={3}
                    value={candidate.summary}
                    onChange={(e) => {
                      setCandidate((c) => ({ ...c, summary: e.target.value }))
                      setIsDirty(true)
                    }}
                    className="w-full rounded-md border border-line bg-n-900 px-3 py-2 text-xs leading-relaxed text-n-100 placeholder-n-500 focus:border-blue-500 focus:outline-none"
                    placeholder="Summary of core competencies, quantifiable engineering impact, and tech stack..."
                  />
                </Field>
              </div>

              {/* 2. Experience Card */}
              <div className="rounded-lg border border-line bg-surface p-5 space-y-4 shadow-2xs">
                <div className="flex items-center justify-between border-b border-line pb-3">
                  <div>
                    <p className="text-xs font-semibold tracking-wide text-n-100 uppercase">
                      2. Professional Experience ({experience.length})
                    </p>
                    <p className="text-micro text-n-500">Roles, achievements, and impact bullets</p>
                  </div>
                  <Button size="sm" onClick={handleAddExperience}>
                    <Icon.Plus className="size-3" />
                    <span>Add Role</span>
                  </Button>
                </div>

                <div className="space-y-4">
                  {experience.map((exp, expIdx) => (
                    <div
                      key={exp.id || expIdx}
                      className="rounded-md border border-line bg-n-900/50 p-4 space-y-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-n-200">
                          Role #{expIdx + 1}: {exp.role || 'Untitled Role'} @ {exp.company || 'Company'}
                        </span>
                        <button
                          onClick={() => {
                            setExperience((prev) => prev.filter((_, i) => i !== expIdx))
                            setIsDirty(true)
                          }}
                          className="press text-micro text-bad-400 hover:text-bad-300"
                        >
                          Remove
                        </button>
                      </div>

                      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                        <Field label="Company">
                          <Input
                            value={exp.company || ''}
                            onChange={(e) => {
                              setExperience((prev) =>
                                prev.map((item, i) =>
                                  i === expIdx ? { ...item, company: e.target.value } : item,
                                ),
                              )
                              setIsDirty(true)
                            }}
                            placeholder="e.g. Stripe, Motive, or Acme Corp"
                          />
                        </Field>
                        <Field label="Role Title">
                          <Input
                            value={exp.role || ''}
                            onChange={(e) => {
                              setExperience((prev) =>
                                prev.map((item, i) =>
                                  i === expIdx ? { ...item, role: e.target.value } : item,
                                ),
                              )
                              setIsDirty(true)
                            }}
                            placeholder="e.g. Lead Software Engineer"
                          />
                        </Field>
                        <Field label="Period / Dates">
                          <Input
                            value={exp.period || ''}
                            onChange={(e) => {
                              setExperience((prev) =>
                                prev.map((item, i) =>
                                  i === expIdx ? { ...item, period: e.target.value } : item,
                                ),
                              )
                              setIsDirty(true)
                            }}
                            placeholder="e.g. March 2024 to Present"
                          />
                        </Field>
                        <Field label="Location">
                          <Input
                            value={exp.location || ''}
                            onChange={(e) => {
                              setExperience((prev) =>
                                prev.map((item, i) =>
                                  i === expIdx ? { ...item, location: e.target.value } : item,
                                ),
                              )
                              setIsDirty(true)
                            }}
                            placeholder="e.g. Remote, United States"
                          />
                        </Field>
                      </div>

                      {/* Bullet points */}
                      <div className="space-y-1.5 pt-1">
                        <div className="flex items-center justify-between">
                          <p className="text-micro font-medium text-n-400 uppercase">
                            Bullet Points ({exp.bullets?.length || 0})
                          </p>
                          <button
                            onClick={() => {
                              setExperience((prev) =>
                                prev.map((item, i) =>
                                  i === expIdx
                                    ? {
                                        ...item,
                                        bullets: [...(item.bullets || []), { text: '' }],
                                      }
                                    : item,
                                ),
                              )
                              setIsDirty(true)
                            }}
                            className="press text-micro text-blue-400 hover:text-blue-300"
                          >
                            + Add Bullet
                          </button>
                        </div>

                        {(exp.bullets || []).map((b, bIdx) => (
                          <div key={bIdx} className="flex items-center gap-2">
                            <span className="text-n-500 text-xs">•</span>
                            <input
                              type="text"
                              value={b.text || ''}
                              onChange={(e) => {
                                setExperience((prev) =>
                                  prev.map((item, i) =>
                                    i === expIdx
                                      ? {
                                          ...item,
                                          bullets: item.bullets.map((bullet, bi) =>
                                            bi === bIdx ? { ...bullet, text: e.target.value } : bullet,
                                          ),
                                        }
                                      : item,
                                  ),
                                )
                                setIsDirty(true)
                              }}
                              placeholder="e.g. Architected high-throughput REST APIs reducing query latency by 45%."
                              className="flex-1 rounded border border-line bg-n-950 px-2.5 py-1 text-xs text-n-100 focus:border-blue-500 focus:outline-none"
                            />
                            <button
                              onClick={() => {
                                setExperience((prev) =>
                                  prev.map((item, i) =>
                                    i === expIdx
                                      ? {
                                          ...item,
                                          bullets: item.bullets.filter((_, bi) => bi !== bIdx),
                                        }
                                      : item,
                                  ),
                                )
                                setIsDirty(true)
                              }}
                              className="press p-1 text-n-500 hover:text-n-300"
                              title="Delete bullet"
                            >
                              ✕
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 3. Projects Card */}
              <div className="rounded-lg border border-line bg-surface p-5 space-y-4 shadow-2xs">
                <div className="flex items-center justify-between border-b border-line pb-3">
                  <div>
                    <p className="text-xs font-semibold tracking-wide text-n-100 uppercase">
                      3. Projects ({projects.length})
                    </p>
                    <p className="text-micro text-n-500">Key systems, technologies, and achievements</p>
                  </div>
                  <Button size="sm" onClick={handleAddProject}>
                    <Icon.Plus className="size-3" />
                    <span>Add Project</span>
                  </Button>
                </div>

                <div className="space-y-4">
                  {projects.map((proj, pIdx) => (
                    <div
                      key={proj.id || pIdx}
                      className="rounded-md border border-line bg-n-900/50 p-4 space-y-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-n-200">
                          Project #{pIdx + 1}: {proj.name || 'Untitled Project'}
                        </span>
                        <button
                          onClick={() => {
                            setProjects((prev) => prev.filter((_, i) => i !== pIdx))
                            setIsDirty(true)
                          }}
                          className="press text-micro text-bad-400 hover:text-bad-300"
                        >
                          Remove
                        </button>
                      </div>

                      <div className="grid gap-2 sm:grid-cols-3">
                        <Field label="Project Name">
                          <Input
                            value={proj.name || ''}
                            onChange={(e) => {
                              setProjects((prev) =>
                                prev.map((item, i) =>
                                  i === pIdx ? { ...item, name: e.target.value } : item,
                                ),
                              )
                              setIsDirty(true)
                            }}
                            placeholder="e.g. Real-Time Distributed Ledger"
                          />
                        </Field>
                        <Field label="Technologies / Tech Stack">
                          <Input
                            value={proj.tech || ''}
                            onChange={(e) => {
                              setProjects((prev) =>
                                prev.map((item, i) =>
                                  i === pIdx ? { ...item, tech: e.target.value } : item,
                                ),
                              )
                              setIsDirty(true)
                            }}
                            placeholder="e.g. React, Node.js, WebSocket, PostgreSQL"
                          />
                        </Field>
                        <Field label="Period / Date">
                          <Input
                            value={proj.period || ''}
                            onChange={(e) => {
                              setProjects((prev) =>
                                prev.map((item, i) =>
                                  i === pIdx ? { ...item, period: e.target.value } : item,
                                ),
                              )
                              setIsDirty(true)
                            }}
                            placeholder="e.g. 2025"
                          />
                        </Field>
                      </div>

                      {/* Project Bullets */}
                      <div className="space-y-1.5 pt-1">
                        <div className="flex items-center justify-between">
                          <p className="text-micro font-medium text-n-400 uppercase">
                            Bullets ({proj.bullets?.length || 0})
                          </p>
                          <button
                            onClick={() => {
                              setProjects((prev) =>
                                prev.map((item, i) =>
                                  i === pIdx
                                    ? {
                                        ...item,
                                        bullets: [...(item.bullets || []), { text: '' }],
                                      }
                                    : item,
                                ),
                              )
                              setIsDirty(true)
                            }}
                            className="press text-micro text-blue-400 hover:text-blue-300"
                          >
                            + Add Bullet
                          </button>
                        </div>

                        {(proj.bullets || []).map((b, bIdx) => (
                          <div key={bIdx} className="flex items-center gap-2">
                            <span className="text-n-500 text-xs">•</span>
                            <input
                              type="text"
                              value={b.text || ''}
                              onChange={(e) => {
                                setProjects((prev) =>
                                  prev.map((item, i) =>
                                    i === pIdx
                                      ? {
                                          ...item,
                                          bullets: item.bullets.map((bullet, bi) =>
                                            bi === bIdx ? { ...bullet, text: e.target.value } : bullet,
                                          ),
                                        }
                                      : item,
                                  ),
                                )
                                setIsDirty(true)
                              }}
                              placeholder="e.g. Integrated live market data feeds powering real-time analytics."
                              className="flex-1 rounded border border-line bg-n-950 px-2.5 py-1 text-xs text-n-100 focus:border-blue-500 focus:outline-none"
                            />
                            <button
                              onClick={() => {
                                setProjects((prev) =>
                                  prev.map((item, i) =>
                                    i === pIdx
                                      ? {
                                          ...item,
                                          bullets: item.bullets.filter((_, bi) => bi !== bIdx),
                                        }
                                      : item,
                                  ),
                                )
                                setIsDirty(true)
                              }}
                              className="press p-1 text-n-500 hover:text-n-300"
                            >
                              ✕
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 4. Technical Skills Card */}
              <div className="rounded-lg border border-line bg-surface p-5 space-y-4 shadow-2xs">
                <div className="flex items-center justify-between border-b border-line pb-3">
                  <p className="text-xs font-semibold tracking-wide text-n-100 uppercase">
                    4. Technical Skills Categories
                  </p>
                  <button
                    onClick={() => {
                      setSkills((prev) => [...prev, { line: '' }])
                      setIsDirty(true)
                    }}
                    className="press text-micro text-blue-400 hover:text-blue-300"
                  >
                    + Add Category Line
                  </button>
                </div>

                <div className="space-y-2">
                  {skills.map((s, sIdx) => (
                    <div key={sIdx} className="flex items-center gap-2">
                      <Input
                        value={s.line || ''}
                        onChange={(e) => {
                          setSkills((prev) =>
                            prev.map((item, i) => (i === sIdx ? { ...item, line: e.target.value } : item)),
                          )
                          setIsDirty(true)
                        }}
                        placeholder="e.g. Languages: Python, TypeScript, Go, SQL, HTML/CSS"
                      />
                      <button
                        onClick={() => {
                          setSkills((prev) => prev.filter((_, i) => i !== sIdx))
                          setIsDirty(true)
                        }}
                        className="press p-1 text-n-500 hover:text-n-300"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* 5. Education Card */}
              <div className="rounded-lg border border-line bg-surface p-5 space-y-4 shadow-2xs">
                <div className="flex items-center justify-between border-b border-line pb-3">
                  <p className="text-xs font-semibold tracking-wide text-n-100 uppercase">
                    5. Education ({education.length})
                  </p>
                  <Button size="sm" onClick={handleAddEducation}>
                    <Icon.Plus className="size-3" />
                    <span>Add Degree</span>
                  </Button>
                </div>

                <div className="space-y-3">
                  {education.map((edu, eIdx) => (
                    <div
                      key={eIdx}
                      className="rounded-md border border-line bg-n-900/50 p-4 space-y-2.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-n-200">
                          {edu.degree || 'Degree'} — {edu.institution || 'Institution'}
                        </span>
                        <button
                          onClick={() => {
                            setEducation((prev) => prev.filter((_, i) => i !== eIdx))
                            setIsDirty(true)
                          }}
                          className="press text-micro text-bad-400 hover:text-bad-300"
                        >
                          Remove
                        </button>
                      </div>

                      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                        <Field label="Institution">
                          <Input
                            value={edu.institution || ''}
                            onChange={(e) => {
                              setEducation((prev) =>
                                prev.map((item, i) =>
                                  i === eIdx ? { ...item, institution: e.target.value } : item,
                                ),
                              )
                              setIsDirty(true)
                            }}
                            placeholder="e.g. Stanford University"
                          />
                        </Field>
                        <Field label="Degree">
                          <Input
                            value={edu.degree || ''}
                            onChange={(e) => {
                              setEducation((prev) =>
                                prev.map((item, i) =>
                                  i === eIdx ? { ...item, degree: e.target.value } : item,
                                ),
                              )
                              setIsDirty(true)
                            }}
                            placeholder="e.g. Bachelor of Science in Computer Science"
                          />
                        </Field>
                        <Field label="Period / Dates">
                          <Input
                            value={edu.period || ''}
                            onChange={(e) => {
                              setEducation((prev) =>
                                prev.map((item, i) =>
                                  i === eIdx ? { ...item, period: e.target.value } : item,
                                ),
                              )
                              setIsDirty(true)
                            }}
                            placeholder="e.g. August 2022 to July 2026"
                          />
                        </Field>
                        <Field label="Location">
                          <Input
                            value={edu.location || ''}
                            onChange={(e) => {
                              setEducation((prev) =>
                                prev.map((item, i) =>
                                  i === eIdx ? { ...item, location: e.target.value } : item,
                                ),
                              )
                              setIsDirty(true)
                            }}
                            placeholder="e.g. Stanford, CA"
                          />
                        </Field>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Bottom Action Buttons */}
              <div className="flex items-center justify-end gap-3 pt-2">
                <Button
                  variant="ghost"
                  disabled={!isDirty || saving}
                  onClick={handleCancel}
                >
                  Cancel
                </Button>
                <Button variant="primary" busy={saving} onClick={handleSaveAll}>
                  Update Profile
                </Button>
              </div>
            </m.div>
          )}

          {/* STYLE & TYPOGRAPHY EDITOR */}
          {(activeView === 'split' || activeView === 'style') && (
            <m.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={springFor()}
              className="space-y-4"
            >
              <div className="rounded-lg border border-line bg-surface p-5 space-y-4 shadow-2xs">
                <p className="text-xs font-semibold text-n-100 uppercase tracking-wide border-b border-line pb-2">
                  Typography & Layout Settings
                </p>

                <Field label="Template Density">
                  <Segmented
                    ariaLabel="Template density"
                    value={opts.template}
                    onChange={(v) => setStyleOption({ template: v })}
                    options={[
                      { value: 'standard', label: 'Standard' },
                      { value: 'compact', label: 'Compact' },
                    ]}
                  />
                </Field>

                <div className="grid grid-cols-2 gap-3">
                  <Field label="Font Family">
                    <Select
                      value={opts.font}
                      onChange={(e) => setStyleOption({ font: e.target.value })}
                    >
                      {FONTS.map(([v, l]) => (
                        <option key={v} value={v}>
                          {l}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Font Size">
                    <Select
                      value={opts.font_size}
                      onChange={(e) => setStyleOption({ font_size: Number(e.target.value) })}
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
                    onChange={(v) => setStyleOption({ align: v })}
                    options={[
                      { value: 'left', label: 'Ragged' },
                      { value: 'justified', label: 'Justified' },
                    ]}
                  />
                </Field>

                <Switch
                  checked={opts.fit_one_page}
                  onChange={(v) => setStyleOption({ fit_one_page: v })}
                  label="Fit to one page"
                  hint="Trims toward a single page, never below the bullet floors."
                />
              </div>

              {/* Section Order */}
              <div className="rounded-lg border border-line bg-surface p-5 space-y-3 shadow-2xs">
                <div className="flex items-center justify-between border-b border-line pb-2">
                  <p className="text-xs font-semibold text-n-100 uppercase tracking-wide">
                    Section Order
                  </p>
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
                          onClick={() => moveSection(key, -1)}
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
                          onClick={() => moveSection(key, 1)}
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
            </m.div>
          )}
        </div>

        {/* Right / Live PDF Viewer */}
        {(activeView === 'split' || activeView === 'style') && (
          <div className="space-y-3 sticky top-6">
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
              <span>ATS Standard: Jake Gutierrez Overleaf LaTeX</span>
              {url ? (
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="press inline-flex items-center gap-1.5 text-blue-400 hover:text-blue-300 hover:underline"
                >
                  <Icon.Doc className="size-3.5" />
                  <span>Open in browser tab</span>
                </a>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
