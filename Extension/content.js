/*
  Jobenzy In-Page Content Script (Manifest v3)
  Extracts active job metadata straight from the live DOM and injects 1-click tracking.
*/

const BACKEND_HOSTS = ['http://127.0.0.1:8000', 'http://localhost:8000']

function extractJobDetails() {
  const url = window.location.href
  const host = window.location.hostname.toLowerCase()

  let title = ''
  let company = ''
  let location = ''
  let description = ''
  let applyUrl = url
  let source = 'extension'

  if (host.includes('linkedin.com')) {
    source = 'linkedin'
    title = document.querySelector(
      '.job-details-jobs-unified-top-card__job-title, .jobs-unified-top-card__job-title, h1.topcard__title, .t-24.job-details-jobs-unified-top-card__job-title, h1'
    )?.innerText?.trim() || ''

    company = document.querySelector(
      '.job-details-jobs-unified-top-card__company-name, .jobs-unified-top-card__company-name, .topcard__org-name-link, .job-details-jobs-unified-top-card__primary-description-container a'
    )?.innerText?.trim() || ''

    location = document.querySelector(
      '.job-details-jobs-unified-top-card__bullet, .jobs-unified-top-card__bullet, .topcard__flavor--bullet, .job-details-jobs-unified-top-card__primary-description-container'
    )?.innerText?.trim() || ''

    description = document.querySelector(
      '.jobs-description__content, .jobs-box__html-content, #job-details, .description__text'
    )?.innerText?.trim() || ''

    const extApply = document.querySelector('.jobs-apply-button--top-card a, a.jobs-apply-button')
    if (extApply && extApply.href) applyUrl = extApply.href

  } else if (host.includes('indeed.com')) {
    source = 'indeed'
    title = document.querySelector(
      '[data-testid="jobsearch-JobInfoHeader-title"], .jobsearch-JobInfoHeader-title, h1'
    )?.innerText?.trim() || ''

    company = document.querySelector(
      '[data-testid="inlineHeader-companyName"], .jobsearch-CompanyInfoContainer a, [data-company-name="true"]'
    )?.innerText?.trim() || ''

    location = document.querySelector(
      '[data-testid="inlineHeader-companyLocation"], #jobLocationText'
    )?.innerText?.trim() || ''

    description = document.querySelector(
      '#jobDescriptionText, .jobsearch-jobDescriptionText'
    )?.innerText?.trim() || ''

  } else if (host.includes('glassdoor.com')) {
    source = 'glassdoor'
    title = document.querySelector('[data-test="job-title"], .JobDetails_jobTitle__rw_s8, h1')?.innerText?.trim() || ''
    company = document.querySelector('[data-test="employer-name"], .JobDetails_companyName__x69fv')?.innerText?.trim() || ''
    location = document.querySelector('[data-test="location"], .JobDetails_location__mSg5h')?.innerText?.trim() || ''
    description = document.querySelector('.JobDetails_jobDescription__uW_fK, [data-test="job-description"]')?.innerText?.trim() || ''

  } else if (host.includes('wellfound.com')) {
    source = 'wellfound'
    title = document.querySelector('h1')?.innerText?.trim() || ''
    company = document.querySelector('h2, [class*="companyName"]')?.innerText?.trim() || ''
    description = document.querySelector('[class*="jobDescription"], main')?.innerText?.trim() || ''

  } else if (host.includes('greenhouse.io') || host.includes('gh_jid')) {
    source = 'greenhouse'
    title = document.querySelector('.app-title, h1.heading, h1')?.innerText?.trim() || ''
    company = document.querySelector('.company-name, .sub-heading')?.innerText?.trim() || ''
    location = document.querySelector('.location')?.innerText?.trim() || ''
    description = document.querySelector('#content, .content, main')?.innerText?.trim() || ''

  } else if (host.includes('lever.co')) {
    source = 'lever'
    title = document.querySelector('.posting-headline h2, h2')?.innerText?.trim() || ''
    company = document.querySelector('.posting-headline .org, .main-header-logo img')?.alt || ''
    location = document.querySelector('.posting-categories .location')?.innerText?.trim() || ''
    description = document.querySelector('.section-wrapper.page-full-width, .posting-description')?.innerText?.trim() || ''

  } else if (host.includes('ashbyhq.com')) {
    source = 'ashby'
    title = document.querySelector('h1')?.innerText?.trim() || ''
    company = document.querySelector('title')?.innerText?.split('-')[0]?.trim() || ''
    description = document.querySelector('.ashby-job-posting-description, main')?.innerText?.trim() || ''

  } else {
    // Generic fallback for custom career pages / Workday
    title = document.querySelector('h1, meta[property="og:title"]')?.innerText || document.title || ''
    description = document.querySelector('main, article, #job-description, .job-description')?.innerText || document.body.innerText.slice(0, 8000)
    company = document.querySelector('meta[property="og:site_name"]')?.content || window.location.hostname.replace('www.', '').split('.')[0]
  }

  return {
    url,
    title: title.replace(/\s+/g, ' ').trim(),
    company: company.replace(/\s+/g, ' ').trim(),
    location: location.replace(/\s+/g, ' ').trim(),
    description: description.trim(),
    apply_url: applyUrl,
    source,
  }
}

// Listen for requests from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getJobDetails') {
    sendResponse(extractJobDetails())
  }
})

// Send extracted job directly to local backend
async function sendToJobenzy(data) {
  for (const host of BACKEND_HOSTS) {
    try {
      const res = await fetch(`${host}/api/agent/extension/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      const json = await res.json()
      return { ok: res.ok, status: res.status, data: json }
    } catch {
      continue
    }
  }
  return { ok: false, status: 0, error: 'Jobenzy is not running locally.' }
}

function showToast(msg) {
  const existing = document.querySelector('.jobenzy-toast')
  if (existing) existing.remove()
  const toast = document.createElement('div')
  toast.className = 'jobenzy-toast'
  toast.textContent = msg
  document.body.appendChild(toast)
  setTimeout(() => toast.remove(), 4500)
}

// Inject floating action button if on a recognized job page
function injectFloatingButton() {
  if (document.getElementById('jobenzy-floating-btn')) return

  const isJobPage =
    window.location.href.includes('/jobs/') ||
    window.location.href.includes('/job/') ||
    window.location.href.includes('/viewjob') ||
    window.location.href.includes('greenhouse.io') ||
    window.location.href.includes('lever.co') ||
    window.location.href.includes('ashbyhq.com') ||
    window.location.href.includes('myworkdayjobs.com')

  if (!isJobPage) return

  const btn = document.createElement('div')
  btn.id = 'jobenzy-floating-btn'
  btn.innerHTML = `<span class="jobenzy-icon">⚡</span> <span>Track in Jobenzy</span>`

  btn.addEventListener('click', async (e) => {
    e.stopPropagation()
    const job = extractJobDetails()
    if (!job.title && !job.description) {
      showToast('Could not find job details on this page.')
      return
    }

    btn.className = 'loading'
    btn.innerHTML = `<span class="jobenzy-icon">⏳</span> <span>Tracking…</span>`

    const res = await sendToJobenzy(job)

    if (res.ok && res.data.created) {
      btn.className = 'success'
      const scoreText = res.data.fitScore ? ` (Score: ${Math.round(res.data.fitScore)})` : ''
      btn.innerHTML = `<span class="jobenzy-icon">✓</span> <span>Tracked${scoreText}</span>`
      showToast(`Tracked: ${res.data.title || 'Job'} at ${res.data.company || 'Company'}${scoreText}`)
    } else if (res.ok) {
      btn.className = 'already'
      btn.innerHTML = `<span class="jobenzy-icon">ℹ</span> <span>Already Tracked</span>`
      showToast(`Already tracked: ${res.data.title || 'Job'}`)
    } else {
      btn.className = 'error'
      btn.innerHTML = `<span class="jobenzy-icon">✕</span> <span>Not Tracked</span>`
      showToast(res.data?.detail || res.error || 'Failed to send to Jobenzy')
    }

    setTimeout(() => {
      btn.className = ''
      btn.innerHTML = `<span class="jobenzy-icon">⚡</span> <span>Track in Jobenzy</span>`
    }, 4000)
  })

  document.body.appendChild(btn)
}

// Run injection when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', injectFloatingButton)
} else {
  injectFloatingButton()
}

// Re-check on URL changes (SPA navigation on LinkedIn/Indeed)
let lastUrl = location.href
new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href
    setTimeout(injectFloatingButton, 1000)
  }
}).observe(document, { subtree: true, childList: true })

