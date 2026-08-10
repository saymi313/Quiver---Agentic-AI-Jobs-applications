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

  analyze: ({ resumeFile, jdText, jdFile }) => {
    const form = new FormData()
    form.append('resume', resumeFile)
    form.append('jd_text', jdText || '')
    if (jdFile) form.append('jd_file', jdFile)
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
  agentJobs: ({ limit = 300, status, category, source, q } = {}) => {
    const p = new URLSearchParams({ limit: String(limit) })
    if (status) p.set('status', status)
    if (category) p.set('category', category)
    if (source) p.set('source', source)
    if (q) p.set('q', q)
    return fetch(`${BASE}/api/agent/jobs?${p}`).then(handle)
  },

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
}
