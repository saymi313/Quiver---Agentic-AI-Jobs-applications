/*
  One click, one request, one honest answer.

  The extension holds no state and no credentials: it posts the current tab's
  URL to Jobenzy running on this machine and reports exactly what came back.
  Everything that decides whether the posting is real, readable or closed
  already lives in the backend, and duplicating any of it here would give two
  places to fix the next time a board changes.
*/

const HOSTS = ['http://127.0.0.1:8000', 'http://localhost:8000']

const urlEl = document.getElementById('url')
const goEl = document.getElementById('go')
const outEl = document.getElementById('out')

let current = ''

chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
  current = tab?.url || ''
  urlEl.textContent = current || 'No page open'
  goEl.disabled = !/^https?:\/\//i.test(current)
})

function show(tone, title, detail) {
  outEl.innerHTML = ''
  const box = document.createElement('div')
  box.className = `result ${tone}`
  const head = document.createElement('b')
  head.textContent = title
  box.appendChild(head)
  if (detail) {
    const meta = document.createElement('div')
    meta.className = 'meta'
    meta.textContent = detail
    box.appendChild(meta)
  }
  outEl.appendChild(box)
}

async function getActiveTabDOM(tabId) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, { action: 'getJobDetails' }, (response) => {
      if (chrome.runtime.lastError || !response) {
        resolve(null)
      } else {
        resolve(response)
      }
    })
  })
}

async function post(host, jobData) {
  const isRich = jobData && (jobData.title || jobData.description)
  const endpoint = isRich ? `${host}/api/agent/extension/import` : `${host}/api/agent/job-from-url`
  const payload = isRich ? jobData : { url: current }

  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await res.json().catch(() => ({}))
  return { res, body }
}

goEl.addEventListener('click', async () => {
  goEl.disabled = true
  goEl.textContent = 'Reading the posting…'
  outEl.innerHTML = ''

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  let jobData = null
  if (tab?.id) {
    jobData = await getActiveTabDOM(tab.id)
  }

  let reached = false
  try {
    for (const host of HOSTS) {
      let attempt
      try {
        attempt = await post(host, jobData)
      } catch {
        continue
      }
      reached = true
      const { res, body } = attempt

      if (res.ok && body.created) {
        show(
          'ok',
          body.title || 'Tracked',
          [body.company, body.category?.replace(/_/g, ' '),
           body.fitScore ? `scored ${Math.round(body.fitScore)}` : null]
            .filter(Boolean)
            .join(' · '),
        )
      } else if (res.ok) {
        show('info', 'Already tracked', body.title || '')
      } else {
        show('bad', 'Not tracked', body.detail || `${res.status} ${res.statusText}`)
      }
      break
    }

    if (!reached) {
      show(
        'bad',
        'Jobenzy is not running',
        'Start it from the Backend folder with python run_dashboard.py, then try again.',
      )
    }
  } finally {
    goEl.disabled = false
    goEl.textContent = 'Track it'
  }
})
