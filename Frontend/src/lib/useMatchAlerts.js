import { useEffect, useRef } from 'react'
import { api } from './api'

/*
  Desktop notifications for a strong new match.

  The browser half of FR-F7. While the dashboard is open this polls for roles at
  or above the score threshold and raises a native notification for any it has
  not shown before — so a scheduled scan that lands while the tab sits in the
  background still surfaces, without waiting to be looked at. The email half
  (agent/notify.py) covers the case where nothing is open at all.

  What "before" means is kept on the client, in localStorage, so it never
  competes with the server's `notified_at` that the email channel owns. Two
  channels, two independent memories, so turning one on or off never doubles or
  silences the other.
*/

const SEEN_KEY = 'quiver.notified.job.ids'
const POLL_MS = 90_000

function loadSeen() {
  try {
    return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || '[]'))
  } catch {
    return new Set()
  }
}

function saveSeen(set) {
  try {
    // Keep the set bounded; only the most recent ids matter for "new".
    localStorage.setItem(SEEN_KEY, JSON.stringify([...set].slice(-400)))
  } catch {
    /* private mode or storage disabled — notifications simply repeat, no crash */
  }
}

export function useMatchAlerts({ enabled, desktop, minScore }) {
  const seen = useRef(null)
  const primed = useRef(false)

  useEffect(() => {
    if (!enabled || !desktop) return
    if (typeof Notification === 'undefined') return

    if (Notification.permission === 'default') {
      Notification.requestPermission().catch(() => {})
    }
    if (seen.current === null) seen.current = loadSeen()

    let alive = true

    const check = async () => {
      if (Notification.permission !== 'granted') return
      let rows
      try {
        const d = await api.agentJobs({ status: 'matched', min_score: minScore || 75, limit: 30 })
        rows = d.rows || []
      } catch {
        return
      }
      if (!alive) return

      const fresh = rows.filter((r) => !seen.current.has(r.id))
      fresh.forEach((r) => seen.current.add(r.id))

      // The first pass only learns what already exists — it does not fire for a
      // backlog the user has not seen the app announce. Real-time alerts start
      // from the second poll onward.
      if (primed.current && fresh.length) {
        const top = fresh[0]
        const more = fresh.length - 1
        const note = new Notification(
          fresh.length === 1 ? 'New match on Quiver' : `${fresh.length} new matches on Quiver`,
          {
            body:
              `${Math.round(top.fit_score || 0)} · ${top.title}` +
              (top.company_name ? ` — ${top.company_name}` : '') +
              (more ? ` and ${more} more` : ''),
            tag: 'quiver-match',
          },
        )
        note.onclick = () => {
          window.focus()
          note.close()
        }
      }
      primed.current = true
      saveSeen(seen.current)
    }

    check()
    const timer = setInterval(check, POLL_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [enabled, desktop, minScore])
}
