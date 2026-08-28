/*
  Jobenzy In-Page Content Script & Autonomous Auto-Applier (Manifest v3)
  Extracts job metadata from DOM & autonomously autofills application forms in-tab.
*/

const BACKEND_HOSTS = ['http://127.0.0.1:8000', 'http://localhost:8000']

// --------------------------------------------------------------------------
// 1. Job Metadata Extraction
// --------------------------------------------------------------------------

function extractJobDetails() {
  const url = window.location.href.split('#')[0]
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

// --------------------------------------------------------------------------
// 2. Local Backend Communication
// --------------------------------------------------------------------------

async function fetchFromJobenzy(path, options = {}) {
  for (const host of BACKEND_HOSTS) {
    try {
      const res = await fetch(`${host}${path}`, options)
      if (res.ok) {
        return await res.json()
      }
    } catch {
      continue
    }
  }
  return null
}

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

// --------------------------------------------------------------------------
// 3. Autonomous In-Tab Autofill Engine
// --------------------------------------------------------------------------

function simulateInput(el, value) {
  if (!el || value === undefined || value === null) return
  el.focus()
  el.value = value
  el.dispatchEvent(new Event('input', { bubbles: true }))
  el.dispatchEvent(new Event('change', { bubbles: true }))
  el.dispatchEvent(new Event('blur', { bubbles: true }))
  el.style.borderColor = '#26a37f'
  el.style.backgroundColor = 'rgba(38, 163, 127, 0.06)'
}

function fieldMatches(el, keywords) {
  const text = [
    el.name || '',
    el.id || '',
    el.getAttribute('placeholder') || '',
    el.getAttribute('aria-label') || '',
    el.getAttribute('autocomplete') || '',
    el.closest('label')?.innerText || '',
    el.closest('.field, .form-group, [class*="field"], [class*="input"], [class*="form-row"]')?.innerText || '',
  ].join(' ').toLowerCase()

  return keywords.some((kw) => text.includes(kw.toLowerCase()))
}

async function runAutonomousAutofill() {
  showToast('Connecting to Jobenzy autonomous engine…')

  const profile = await fetchFromJobenzy('/api/agent/profile')
  if (!profile) {
    showToast('Jobenzy backend is not running on localhost:8000')
    return
  }

  const nameParts = (profile.full_name || profile.name || '').split(' ')
  const firstName = profile.first_name || nameParts[0] || ''
  const lastName = profile.last_name || nameParts.slice(1).join(' ') || ''
  const fullName = profile.full_name || `${firstName} ${lastName}`.trim()
  const email = profile.email || ''
  const phone = profile.phone || ''
  const linkedin = profile.linkedin || ''
  const github = profile.github || ''
  const portfolio = profile.portfolio || profile.website || ''
  const location = profile.location || profile.city || 'Islamabad, Pakistan'

  let filledCount = 0

  const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea, select'))

  for (const el of inputs) {
    // Already filled
    if (el.value && el.value.trim() !== '') continue

    // First Name
    if (fieldMatches(el, ['first name', 'firstname', 'given-name', 'fname'])) {
      simulateInput(el, firstName)
      filledCount++
    }
    // Last Name
    else if (fieldMatches(el, ['last name', 'lastname', 'family-name', 'lname', 'surname'])) {
      simulateInput(el, lastName)
      filledCount++
    }
    // Full Name
    else if (fieldMatches(el, ['full name', 'fullname', 'name']) && !fieldMatches(el, ['company', 'file', 'user'])) {
      simulateInput(el, fullName)
      filledCount++
    }
    // Email
    else if (el.type === 'email' || fieldMatches(el, ['email', 'e-mail'])) {
      simulateInput(el, email)
      filledCount++
    }
    // Phone
    else if (el.type === 'tel' || fieldMatches(el, ['phone', 'mobile', 'telephone', 'contact number'])) {
      simulateInput(el, phone)
      filledCount++
    }
    // LinkedIn
    else if (fieldMatches(el, ['linkedin', 'urls[linkedin]', 'linkedin profile'])) {
      simulateInput(el, linkedin)
      filledCount++
    }
    // GitHub
    else if (fieldMatches(el, ['github', 'urls[github]', 'github profile'])) {
      simulateInput(el, github)
      filledCount++
    }
    // Portfolio / Website
    else if (fieldMatches(el, ['portfolio', 'website', 'personal site', 'urls[portfolio]'])) {
      simulateInput(el, portfolio)
      filledCount++
    }
    // Location / City
    else if (fieldMatches(el, ['location', 'city', 'address', 'current city'])) {
      simulateInput(el, location)
      filledCount++
    }
    // Experience years
    else if (fieldMatches(el, ['years of experience', 'years experience', 'total experience'])) {
      simulateInput(el, String(profile.years_experience || '3'))
      filledCount++
    }
    // Notice period
    else if (fieldMatches(el, ['notice period', 'how soon can you start', 'availability'])) {
      simulateInput(el, 'Immediately / 2 weeks')
      filledCount++
    }
    // Work authorization / Sponsorship
    else if (el.tagName === 'SELECT') {
      if (fieldMatches(el, ['sponsorship', 'visa', 'require sponsorship'])) {
        for (const opt of el.options) {
          if (opt.text.toLowerCase().includes('no') || opt.value.toLowerCase().includes('no')) {
            el.value = opt.value
            simulateInput(el, opt.value)
            filledCount++
            break
          }
        }
      } else if (fieldMatches(el, ['authorized to work', 'legally authorized'])) {
        for (const opt of el.options) {
          if (opt.text.toLowerCase().includes('yes') || opt.value.toLowerCase().includes('yes')) {
            el.value = opt.value
            simulateInput(el, opt.value)
            filledCount++
            break
          }
        }
      }
    }
  }

  showToast(`Autofilled ${filledCount} field${filledCount === 1 ? '' : 's'} with Jobenzy AI`)
}

// --------------------------------------------------------------------------
// 4. UI Overlay & Floating Actions
// --------------------------------------------------------------------------

function showToast(msg) {
  const existing = document.querySelector('.jobenzy-toast')
  if (existing) existing.remove()
  const toast = document.createElement('div')
  toast.className = 'jobenzy-toast'
  toast.textContent = msg
  document.body.appendChild(toast)
  setTimeout(() => toast.remove(), 5000)
}

function injectFloatingWidget() {
  if (document.getElementById('jobenzy-floating-container')) return

  const container = document.createElement('div')
  container.id = 'jobenzy-floating-container'
  container.innerHTML = `
    <div id="jobenzy-floating-btn" title="Track in Jobenzy">
      <span class="jobenzy-icon">J</span>
      <span>Track</span>
    </div>
    <div id="jobenzy-apply-btn" title="Autofill and Apply on this page">
      <span class="jobenzy-icon">⚡</span>
      <span>Auto-Apply</span>
    </div>
  `

  const trackBtn = container.querySelector('#jobenzy-floating-btn')
  const applyBtn = container.querySelector('#jobenzy-apply-btn')

  trackBtn.addEventListener('click', async (e) => {
    e.stopPropagation()
    const job = extractJobDetails()
    if (!job.title && !job.description) {
      showToast('Could not find job details on this page.')
      return
    }
    trackBtn.className = 'loading'
    trackBtn.innerHTML = `<span class="jobenzy-icon">…</span> <span>Tracking…</span>`

    const res = await sendToJobenzy(job)
    if (res.ok && res.data.created) {
      trackBtn.className = 'success'
      const scoreText = res.data.fitScore ? ` (${Math.round(res.data.fitScore)}% match)` : ''
      trackBtn.innerHTML = `<span class="jobenzy-icon">✓</span> <span>Tracked</span>`
      showToast(`Tracked: ${res.data.title || 'Job'}${scoreText}`)
    } else if (res.ok) {
      trackBtn.className = 'already'
      trackBtn.innerHTML = `<span class="jobenzy-icon">✓</span> <span>Tracked</span>`
      showToast(`Already tracked in Jobenzy`)
    } else {
      trackBtn.className = 'error'
      trackBtn.innerHTML = `<span class="jobenzy-icon">✕</span> <span>Error</span>`
      showToast(res.data?.detail || res.error || 'Failed to connect to Jobenzy')
    }

    setTimeout(() => {
      trackBtn.className = ''
      trackBtn.innerHTML = `<span class="jobenzy-icon">J</span> <span>Track</span>`
    }, 3500)
  })

  applyBtn.addEventListener('click', (e) => {
    e.stopPropagation()
    runAutonomousAutofill()
  })

  document.body.appendChild(container)

  // Check if auto-apply was requested via URL hash
  if (window.location.hash.includes('jobenzy-apply')) {
    setTimeout(runAutonomousAutofill, 1200)
  }
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', injectFloatingWidget)
} else {
  injectFloatingWidget()
}

// Re-check on URL changes (SPA navigation)
let lastUrl = location.href
new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href
    setTimeout(injectFloatingWidget, 1000)
  }
}).observe(document, { subtree: true, childList: true })
