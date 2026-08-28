const BASE = ''

async function handle(res) {
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message)
  }
  return res.json()
}

export const api = {
  health: () => fetch(`${BASE}/api/health`).then(handle),

  defaultResume: (category) =>
    fetch(`${BASE}/api/ats/default-resume` + (category ? `?category=${encodeURIComponent(category)}` : '')).then(handle),

  analyze: ({ resumeFile, jdText, jdFile, category }) => {
    const form = new FormData()
    if (resumeFile) {
      form.append('resume', resumeFile)
    } else {
      form.append('use_default', 'true')
    }
    form.append('jd_text', jdText || '')
    if (jdFile) form.append('jd_file', jdFile)
    if (category) form.append('category', category)
    return fetch(`${BASE}/api/ats/analyze`, { method: 'POST', body: form }).then(handle)
  },

  build: (payload) =>
    fetch(`${BASE}/api/ats/build`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(handle),

  overview: () => fetch(`${BASE}/api/auto/overview`).then(handle),
  activity: () => fetch(`${BASE}/api/auto/activity`).then(handle),

  run: (payload) =>
    fetch(`${BASE}/api/auto/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(handle),

  stop: (jobId) => fetch(`${BASE}/api/auto/stop/${jobId}`, { method: 'POST' }).then(handle),

  streamUrl: (jobId, cursor = 0) => `${BASE}/api/auto/jobs/${jobId}/stream?cursor=${cursor}`,

  // ---- agent ----
  agentOverview: () => fetch(`${BASE}/api/agent/overview`).then(handle),

  agentData: (kind, limit = 100, status) =>
    fetch(
      `${BASE}/api/agent/data?kind=${encodeURIComponent(kind)}&limit=${limit}` +
        (status ? `&status=${encodeURIComponent(status)}` : ''),
    ).then(handle),

  // The tracked jobs table: rows plus the facet counts the filters are built from.
  /*
    Every filter the endpoint understands, forwarded by name.

    This used to destructure four known keys and drop the rest, which meant a
    new filter could be built, wired and shipped without doing anything at all:
    the request went out looking exactly as it had before. Passing the object
    through means the query and the endpoint's signature are the only two
    things that have to agree.

    `false` is a real value here — `remote=false` means on-site — so only
    undefined, null and the empty string are treated as "not set".
  */
  agentJobs: ({ limit = 300, ...filters } = {}) => {
    const p = new URLSearchParams({ limit: String(limit) })
    for (const [key, value] of Object.entries(filters)) {
      if (value === undefined || value === null || value === '') continue
      p.set(key, String(value))
    }
    return fetch(`${BASE}/api/agent/jobs?${p}`).then(handle)
  },

  agentClearJobs: ({ keepApplied = true, keepSaved = true } = {}) =>
    fetch(`${BASE}/api/agent/jobs/clear`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: true, keep_applied: keepApplied, keep_saved: keepSaved }),
    }).then(handle),

  agentClearTracker: () =>
    fetch(`${BASE}/api/agent/tracker/clear`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: true }),
    }).then(handle),

  agentResearch: () => fetch(`${BASE}/api/agent/research`).then(handle),
  agentResearchCompany: (id) => fetch(`${BASE}/api/agent/research/${id}`).then(handle),

  // ---- employer-account credentials ----
  agentCredentials: () => fetch(`${BASE}/api/agent/credentials`).then(handle),

  agentSetCredential: (domain, username, password) =>
    fetch(`${BASE}/api/agent/credentials`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, username, password }),
    }).then(handle),

  agentDeleteCredential: (domain) =>
    fetch(`${BASE}/api/agent/credentials/${encodeURIComponent(domain)}`, {
      method: 'DELETE',
    }).then(handle),

  agentSetAppPassword: ({ password = '', generate = false }) =>
    fetch(`${BASE}/api/agent/application-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password, generate }),
    }).then(handle),

  // Hand back what a site is waiting on — a one-time code, or a confirmation
  // link a freshly created account needs. Pass { code } or { link }.
  agentSubmitInput: (jobId, payload) =>
    fetch(`${BASE}/api/agent/job/${jobId}/otp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(handle),

  agentSubmitOtp: (jobId, code) =>
    fetch(`${BASE}/api/agent/job/${jobId}/otp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    }).then(handle),

  agentInputRequired: () =>
    fetch(`${BASE}/api/agent/input-required`).then(handle),

  agentSaveJob: (jobId, saved = true) =>
    fetch(`${BASE}/api/agent/job/${jobId}/save?saved=${saved}`, { method: 'POST' }).then(handle),

  agentPassJob: (jobId) =>
    fetch(`${BASE}/api/agent/job/${jobId}/pass`, { method: 'POST' }).then(handle),

  agentScreenshotUrl: (name) => `${BASE}/api/agent/screenshot/${encodeURIComponent(name)}`,

  agentResumeUrl: (jobId, fmt = 'pdf', download = false) =>
    `${BASE}/api/agent/resume/${jobId}?fmt=${fmt}${download ? '&download=true' : ''}`,

  agentSettings: (patch) =>
    fetch(`${BASE}/api/agent/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }).then(handle),

  agentLlmTest: () => fetch(`${BASE}/api/agent/llm-test`, { method: 'POST' }).then(handle),

  // ---- track ----
  agentTracker: (limit = 300) => fetch(`${BASE}/api/agent/tracker?limit=${limit}`).then(handle),

  agentInbox: ({ limit = 100, klass, unread, q } = {}) => {
    const p = new URLSearchParams({ limit: String(limit) })
    if (klass) p.set('klass', klass)
    if (unread) p.set('unread', 'true')
    if (q) p.set('q', q)
    return fetch(`${BASE}/api/agent/inbox?${p}`).then(handle)
  },

  agentMessage: (id) => fetch(`${BASE}/api/agent/message/${id}`).then(handle),

  agentCompose: (to, subject, text) =>
    fetch(`${BASE}/api/agent/compose`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to, subject: subject || null, text }),
    }).then(handle),

  agentAddApplication: (body) =>
    fetch(`${BASE}/api/agent/applications`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(handle),

  agentImportApplications: (file) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE}/api/agent/applications/import`, { method: 'POST', body: form }).then(handle)
  },

  agentExportApplicationsUrl: () => `${BASE}/api/agent/applications/export`,

  agentMailbox: () => fetch(`${BASE}/api/agent/mailbox`).then(handle),

  agentReply: (messageId, text, subject) =>
    fetch(`${BASE}/api/agent/message/${messageId}/reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, subject: subject || null }),
    }).then(handle),

  agentSetStage: (appId, status) =>
    fetch(`${BASE}/api/agent/application/${appId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    }).then(handle),

  agentMarkRead: (messageId, read = true) =>
    fetch(`${BASE}/api/agent/message/${messageId}/read?read=${read}`, {
      method: 'POST',
    }).then(handle),

  agentReceipt: (appId) => fetch(`${BASE}/api/agent/receipt/${appId}`).then(handle),

  agentPortals: () => fetch(`${BASE}/api/agent/portals`).then(handle),

  // ---- auto apply ----
  agentProposals: () => fetch(`${BASE}/api/agent/proposals`).then(handle),

  agentDecideProposals: (ids, decision) =>
    fetch(`${BASE}/api/agent/proposals/decide`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids, decision }),
    }).then(handle),

  // ---- resume profiles ----
  agentResumeProfiles: () => fetch(`${BASE}/api/agent/resume-profiles`).then(handle),

  agentCreateProfile: (name, copyFrom = 'main') =>
    fetch(`${BASE}/api/agent/resume-profiles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, copy_from: copyFrom }),
    }).then(handle),

  agentDeleteProfile: (name) =>
    fetch(`${BASE}/api/agent/resume-profiles/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    }).then(handle),

  // ---- resume editor (FR-P11) ----
  agentResumePreview: (profile, options) =>
    fetch(`${BASE}/api/agent/resume-preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile, options }),
    }).then(async (r) => {
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Could not build the preview.')
      return { blob: await r.blob(), pages: r.headers.get('X-Resume-Pages') }
    }),

  agentSaveRender: (name, options) =>
    fetch(`${BASE}/api/agent/resume-profiles/${encodeURIComponent(name)}/render`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ options }),
    }).then(handle),

  agentImportProfile: (name, file) => {
    const form = new FormData()
    form.append('name', name)
    form.append('file', file)
    return fetch(`${BASE}/api/agent/resume-profiles/import`, { method: 'POST', body: form }).then(handle)
  },

  agentSetProfileCategories: (name, categories) =>
    fetch(`${BASE}/api/agent/resume-profiles/${encodeURIComponent(name)}/categories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ categories }),
    }).then(handle),

  agentSetDefaultProfile: (name) =>
    fetch(`${BASE}/api/agent/resume-profiles/${encodeURIComponent(name)}/default`, {
      method: 'POST',
    }).then(handle),

  agentGetProfileData: (name) =>
    fetch(`${BASE}/api/agent/resume-profiles/${encodeURIComponent(name)}/data`).then(handle),

  agentSaveProfileData: (name, data) =>
    fetch(`${BASE}/api/agent/resume-profiles/${encodeURIComponent(name)}/data`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data }),
    }).then(handle),

  // ---- prep ----
  agentJobFromUrl: (url) =>
    fetch(`${BASE}/api/agent/job-from-url`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    }).then(handle),

  agentResumeChanges: (jobId) =>
    fetch(`${BASE}/api/agent/resume/${jobId}/changes`).then(handle),

  agentApproveResume: (jobId, changes) =>
    fetch(`${BASE}/api/agent/resume/${jobId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ changes: changes || null }),
    }).then(handle),

  // ---- core AI features (RAG, Typst, Alumni) ----
  rankBullets: ({ jobDescription, bullets = [], topK = 4 }) =>
    fetch(`${BASE}/api/agent/rag/rank_bullets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_description: jobDescription, bullets, top_k: topK }),
    }).then(handle),

  getAlumniReferrals: ({ companyName, roleTitle, contactName = 'there', almaMater = 'FAST-NUCES', skillsHighlight }) =>
    fetch(`${BASE}/api/agent/outreach/alumni_referral`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company_name: companyName,
        role_title: roleTitle,
        contact_name: contactName,
        alma_mater: almaMater,
        skills_highlight: skillsHighlight,
      }),
    }).then(handle),

  compileTypst: ({ profile, font = 'times', fontSize = 10.0, margins = '0.65in' }) =>
    fetch(`${BASE}/api/agent/resume/typst_compile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile, font, font_size: fontSize, margins }),
    }).then(handle),

  // ---- advanced features ----
  agentJobOutreach: (jobId) => fetch(`${BASE}/api/agent/jobs/${jobId}/outreach`).then(handle),
  agentJobAtsAudit: (jobId) => fetch(`${BASE}/api/agent/jobs/${jobId}/ats-audit`).then(handle),
  agentJobInterviewPrep: (jobId) => fetch(`${BASE}/api/agent/jobs/${jobId}/interview-prep`).then(handle),

  // ---- source portals & integrations ----
  agentSourcesStatus: () => fetch(`${BASE}/api/agent/sources/status`).then(handle),
  agentSourcesFetch: (params) =>
    fetch(`${BASE}/api/agent/sources/fetch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params || {}),
    }).then(handle),
  agentConnectLinkedIn: (data) =>
    fetch(`${BASE}/api/agent/linkedin/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data || {}),
    }).then(handle),

  agentTailorDiff: (jobId) => fetch(`${BASE}/api/agent/tailor/diff?job_id=${jobId}`).then(handle),
  agentRescueResume: (jobId) =>
    fetch(`${BASE}/api/agent/rescue/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId }),
    }).then(handle),
  agentInboxSync: () => fetch(`${BASE}/api/agent/inbox/sync`, { method: 'POST' }).then(handle),
}

