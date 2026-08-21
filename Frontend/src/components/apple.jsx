import { useEffect } from 'react'
import { AnimatePresence, motion as m } from 'motion/react'

import { FADE, prefersReducedMotion, springFor } from '../lib/motion'

/*
  Apple's material components.

  These live apart from the base kit because they share one idea the rest of
  the app does not need: they are surfaces that *float*, and a floating surface
  in Apple's language is a material — translucent, blurred, catching light on
  its top edge — rather than a panel with a shadow bolted on.

  Three rules from the design language govern everything here:

    * Never stack one light translucent surface on another. A sheet may be
      glass because the page behind it is opaque; nothing inside the sheet is
      glass in turn.
    * Dim to focus, separate to keep flow. A task that blocks pairs the
      surface with a scrim and pushes the page back. A panel that runs
      alongside gets translucency and offset, and no scrim at all.
    * Materialize, don't fade. Blur and scale animate together on enter, so
      the surface reads as glass arriving rather than a box turning opaque.
*/

/**
 * A modal sheet: a task that blocks, so the page behind it dims and recedes.
 */
export function Sheet({ open, onClose, title, description, children, footer, wide = false }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    document.addEventListener('keydown', onKey)
    // A page that scrolls behind a modal is the clearest tell that the surface
    // is inline rather than floating.
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [open, onClose])

  const reduced = prefersReducedMotion()

  return (
    <AnimatePresence>
      {open ? (
        <div className="fixed inset-0 z-50 grid place-items-center p-4 sm:p-6">
          <m.div
            className="absolute inset-0 bg-n-100/25"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={FADE}
            onClick={onClose}
          />
          <m.div
            role="dialog"
            aria-modal="true"
            aria-label={typeof title === 'string' ? title : undefined}
            className={`material-thick material-edge relative flex max-h-[85vh] w-full flex-col
              overflow-hidden rounded-lg border border-line ${wide ? 'max-w-4xl' : 'max-w-2xl'}`}
            initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.96, filter: 'blur(14px)' }}
            animate={reduced ? { opacity: 1 } : { opacity: 1, scale: 1, filter: 'blur(0px)' }}
            exit={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.97, filter: 'blur(10px)' }}
            transition={springFor()}
          >
            {title ? (
              <header className="shrink-0 border-b border-line/70 px-5 py-4">
                <h2 className="vibrant text-lg font-semibold">{title}</h2>
                {description ? (
                  <p className="vibrant-secondary mt-1 text-tiny leading-relaxed">{description}</p>
                ) : null}
              </header>
            ) : null}
            <div className="min-h-0 flex-1 overflow-auto px-5 py-4">{children}</div>
            {footer ? (
              <footer className="shrink-0 border-t border-line/70 px-5 py-3">{footer}</footer>
            ) : null}
          </m.div>
        </div>
      ) : null}
    </AnimatePresence>
  )
}

/**
 * Apple's segmented control.
 *
 * For a handful of mutually exclusive views this beats a dropdown on every
 * count: every option is visible without a click, the current one is obvious,
 * and switching is one gesture rather than two. The selected background is a
 * single shared element that springs between segments, so the eye follows it
 * across instead of watching one highlight vanish and another appear.
 */
export function Segmented({ value, onChange, options, ariaLabel, size = 'md' }) {
  const height = size === 'sm' ? 'h-7 text-tiny' : 'h-8 text-sm'
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={`inline-flex items-center gap-0.5 rounded-full bg-n-850 p-0.5 ${height}`}
    >
      {options.map((opt) => {
        const active = value === opt.value
        return (
          <button
            key={opt.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.value)}
            className={`press relative h-full rounded-full px-3 whitespace-nowrap
              ${active ? 'text-n-100' : 'text-n-400 hover:text-n-100'}`}
          >
            {active ? (
              <m.span
                layoutId={`segmented-${ariaLabel || 'default'}`}
                transition={springFor()}
                className="absolute inset-0 -z-10 rounded-full bg-surface shadow-card"
              />
            ) : null}
            <span className={active ? 'font-medium' : ''}>{opt.label}</span>
            {opt.count != null ? (
              <span className="ml-1.5 text-micro tabular-nums opacity-55">{opt.count}</span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}

/*
  Things that come in kinds carry their own hue.

  This is colour that identifies rather than decorates — the same job a Finder
  tag does. After a day you spot the design roles, or the one offer in a
  hundred replies, without reading a word.

  One palette serves every such set. The hues live in `index.css` named for the
  colour, so a set that borrows one is not stuck under another set's name, and
  every tint/ink pair has already been walked to 4.5:1 against itself — a chip
  sits on its tint, not on the page.
*/
const HUE = {
  blue: 'bg-hue-blue text-hue-blue-fg',
  teal: 'bg-hue-teal text-hue-teal-fg',
  purple: 'bg-hue-purple text-hue-purple-fg',
  green: 'bg-hue-green text-hue-green-fg',
  violet: 'bg-hue-violet text-hue-violet-fg',
  pink: 'bg-hue-pink text-hue-pink-fg',
  orange: 'bg-hue-orange text-hue-orange-fg',
  red: 'bg-hue-red text-hue-red-fg',
  amber: 'bg-hue-amber text-hue-amber-fg',
  cyan: 'bg-hue-cyan text-hue-cyan-fg',
  grey: 'bg-n-850 text-n-400',
}

function Chip({ hue, label, title, className = '' }) {
  return (
    <span
      title={title}
      className={`inline-block rounded-full px-2 py-0.5 text-micro font-medium whitespace-nowrap
        ${HUE[hue] || HUE.grey} ${className}`}
    >
      {label}
    </span>
  )
}

const CATEGORY_HUE = {
  backend: 'blue',
  frontend: 'teal',
  fullstack: 'purple',
  software_engineer: 'green',
  ai_engineer: 'violet',
  ai_software_engineer: 'pink',
  product_design: 'orange',
  ui_ux: 'red',
  ui_design: 'amber',
  ux_design: 'cyan',
}

export function CategoryChip({ slug, className = '' }) {
  if (!slug) return null
  const words = slug.replace(/_/g, ' ')
  return <Chip hue={CATEGORY_HUE[slug]} label={words} title={words} className={className} />
}

/*
  A reply's class, coloured by what it means for you rather than by taxonomy:
  green is the offer, red is the no, blue is someone wanting to talk. The
  classes that are merely administrative stay grey, so the ones that are not
  have somewhere to stand out from.
*/
const MESSAGE_HUE = {
  offer: 'green',
  interview: 'blue',
  assessment: 'purple',
  rejection: 'red',
  reminder: 'amber',
  bounce: 'orange',
  verification: 'cyan',
}

export function MessageChip({ klass, label, className = '' }) {
  return (
    <Chip
      hue={MESSAGE_HUE[klass]}
      label={label || klass || 'unsorted'}
      title={klass || undefined}
      className={className}
    />
  )
}

/**
 * The score as a ring, coloured by band.
 *
 * A number in a column is read; a ring is seen, and its colour says whether
 * the number is good before you have read it at all.
 */
export function ScoreRing({ value, size = 42, stroke = 3.5 }) {
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const pct = Math.max(0, Math.min(value || 0, 100)) / 100
  const tone =
    value >= 75
      ? 'text-ok-400'
      : value >= 55
        ? 'text-blue-500'
        : value >= 40
          ? 'text-warn-400'
          : 'text-bad-400'

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-n-100/10"
        />
        <m.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          className={tone}
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference * (1 - pct) }}
          transition={springFor()}
        />
      </svg>
      <span
        className="absolute inset-0 grid place-items-center text-micro font-semibold
          tabular-nums text-n-100"
      >
        {Math.round(value || 0)}
      </span>
    </div>
  )
}

/**
 * The actions for a selection, as a bar that floats over the page.
 *
 * Apple's answer to "you have picked some things, here is what you can do with
 * them" is a surface that arrives over the content rather than one that opens
 * inside it. That is not only the house style — a bar that appears in the flow
 * pushes the list down, so the row you just clicked slides out from under the
 * pointer at the moment you are most likely to click the next one.
 *
 * Floating over the page is also the one place a material is unambiguously
 * right: the thing it obscures is the list it is about, and blurring it is how
 * you can still see that it is there.
 */
export function SelectionBar({ open, children }) {
  const reduced = prefersReducedMotion()
  return (
    <AnimatePresence>
      {open ? (
        <m.div
          className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center p-4"
          initial={reduced ? { opacity: 0 } : { opacity: 0, y: 24, scale: 0.97 }}
          animate={reduced ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
          exit={reduced ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.98 }}
          transition={springFor()}
        >
          <div
            className="material-thick material-edge pointer-events-auto flex flex-wrap
              items-center gap-2.5 rounded-full border border-line py-2 pr-2 pl-4"
          >
            {children}
          </div>
        </m.div>
      ) : null}
    </AnimatePresence>
  )
}

/**
 * A stage in a pipeline, drawn as a filled track.
 *
 * The count answers "how many"; the bar answers "what proportion", which is
 * the question you actually have when scanning five stages at once.
 */
export function StageBar({ label, value, total, tone = 'blue', hint }) {
  const pct = total ? Math.round((value / total) * 100) : 0
  const fill = {
    blue: 'bg-blue-500',
    ok: 'bg-ok-400',
    warn: 'bg-warn-400',
    bad: 'bg-bad-400',
    neutral: 'bg-n-500',
  }[tone]

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-micro font-medium tracking-wide text-n-500 uppercase">{label}</span>
        <span className="text-tiny tabular-nums text-n-400">{pct}%</span>
      </div>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-n-100">{value}</p>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-n-800">
        <m.div
          className={`h-full rounded-full ${fill}`}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={springFor()}
        />
      </div>
      {hint ? <p className="mt-1.5 text-micro text-n-500">{hint}</p> : null}
    </div>
  )
}
