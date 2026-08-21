/*
  One click, one request, one honest answer.

  The extension holds no state and no credentials: it posts the current tab's
  URL to Quiver running on this machine and reports exactly what came back.
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

async function post(host) {
  const res = await fetch(`${host}/api/agent/job-from-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: current }),
  })
  const body = await res.json().catch(() => ({}))
  return { res, body }
}

goEl.addEventListener('click', async () => {
  goEl.disabled = true
  goEl.textContent = 'Reading the posting…'
  outEl.innerHTML = ''

  let reached = false
  try {
    // 127.0.0.1 first, then localhost: which one resolves depends on how the
    // user started uvicorn, and guessing wrong reads as "Quiver is not running".
    for (const host of HOSTS) {
      let attempt
      try {
        attempt = await post(host)
      } catch {
        continue // this host is not listening; try the other spelling
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
        // The backend's own words. It distinguishes a closed posting from an
        // unreadable page, and that distinction is the useful part.
        show('bad', 'Not tracked', body.detail || `${res.status} ${res.statusText}`)
      }
      break
    }

    if (!reached) {
      show(
        'bad',
        'Quiver is not running',
        'Start it from the Backend folder with python run_dashboard.py, then try again.',
      )
    }
  } finally {
    goEl.disabled = false
    goEl.textContent = 'Track it'
  }
})
