/*
  The design kit. Every visual decision in the app resolves to something here.

  Conventions:
    * Content surfaces are opaque and white; `raised`/`sunken` are the one
      grey step up for nested blocks and wells. Only chrome is translucent.
    * Depth is a 1px `line` border. Shadow is reserved for things that float
      above the page, never for panels that sit on it.
    * Radius comes from the tokens in index.css; buttons and chips are pills,
      panels are 12 to 18px. Components pick one and never deviate.
    * Type sizes come from the scale in index.css, each with its own tracking
      and leading. `micro` is for labels only.
    * Near-black is the primary action and nothing else. Blue is selection,
      links and focus. A control that is neither gets grey.
    * Interactive elements define hover / focus / active / disabled together,
      so a new button cannot ship with two of the four.
    * Anything a user can interrupt is animated with a spring from src/lib/
      motion.js, never a CSS transition — a transition always plays out to its
      target before it will accept a new one, which is exactly wrong for a
      panel someone is opening and closing. Colour and press states stay in
      CSS, because they resolve in one step.
*/

import { cloneElement, isValidElement, useEffect, useId, useState } from 'react'
import { AnimatePresence, motion as m } from 'motion/react'

import { springFor } from '../lib/motion'
import { usePress } from '../lib/usePress'

/* ------------------------------------------------------------------ layout */

/** Page header. Every screen opens with exactly one, so the user always
 *  knows where they are and what the screen is for. */
export function PageHead({ title, description, actions }) {
  // iOS's large title, on the web. At the top of a page the heading is a full
  // display line with its description; once you scroll past it, it collapses
  // into a compact material bar carrying just the title and the actions.
  //
  // The compact bar is the fix for a real problem, not decoration: a sticky
  // heading two lines tall left a band of the page showing through itself, so
  // "Settings" and a status chip could be read straight through the word
  // "Jobs". Floating chrome has to be short enough to be chrome.
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    const onScroll = () => setCollapsed(window.scrollY > 72)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <>
      <AnimatePresence>
        {collapsed ? (
          <m.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={springFor()}
            className="material material-edge fixed inset-x-0 top-0 z-40 border-b border-line
              md:left-56"
          >
            <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-2.5
              lg:px-10">
              <span className="vibrant truncate text-base font-semibold">{title}</span>
              {actions ? (
                <div className="flex shrink-0 items-center gap-2">{actions}</div>
              ) : null}
            </div>
          </m.div>
        ) : null}
      </AnimatePresence>

      <div className="flex flex-wrap items-end justify-between gap-4 pb-6">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-semibold text-n-100">{title}</h1>
          {description ? (
            <p className="mt-1.5 text-base leading-relaxed text-n-400">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
    </>
  )
}

/** A titled block within a page. Use `flush` when the body is a table or
 *  console that should meet the border with no padding. */
export function Section({ title, description, actions, children, flush = false, className = '' }) {
  return (
    <section className={`rounded-lg border border-line bg-surface ${className}`}>
      {title || actions ? (
        <header className="flex flex-wrap items-start justify-between gap-3 px-5 py-4">
          <div className="min-w-0">
            {title ? (
              <h2 className="text-sm font-semibold tracking-tight text-n-100">{title}</h2>
            ) : null}
            {description ? (
              <p className="mt-0.5 text-tiny leading-relaxed text-n-400">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </header>
      ) : null}
      {children != null ? (
        <div className={flush ? 'border-t border-line' : 'border-t border-line p-5'}>{children}</div>
      ) : null}
    </section>
  )
}

/** Collapsible section. Configuration lives behind these so a screen opens
 *  showing what you came to do, not every knob that governs it.
 *
 *  The open/close is a spring rather than a CSS transition so it can be
 *  grabbed mid-flight: click twice quickly and it reverses from wherever it
 *  currently is instead of finishing the first move and then undoing it. */
export function Disclosure({ title, description, open, onToggle, children, actions }) {
  return (
    <section className="rounded-lg border border-line bg-surface">
      <header className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
        <button
          onClick={() => onToggle(!open)}
          aria-expanded={open}
          className="group flex min-w-0 items-center gap-2 text-left"
        >
          <m.span animate={{ rotate: open ? 90 : 0 }} transition={springFor()} className="flex">
            <Icon.Chevron className="size-3.5 shrink-0 text-n-500" />
          </m.span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-n-100">
              {title}
            </span>
            {description ? (
              <span className="mt-0.5 block text-tiny text-n-400">{description}</span>
            ) : null}
          </span>
        </button>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </header>
      <AnimatePresence initial={false}>
        {open ? (
          <m.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={springFor()}
            className="overflow-hidden"
          >
            <div className="border-t border-line p-5">{children}</div>
          </m.div>
        ) : null}
      </AnimatePresence>
    </section>
  )
}

/** Label + value, the workhorse for read-only facts. Replaces the stat tiles
 *  that turned every page into a scoreboard. */
export function Metric({ label, value, hint }) {
  return (
    <div>
      <dt className="text-micro font-medium tracking-wide text-n-500 uppercase">{label}</dt>
      <dd className="mt-1 text-lg font-semibold tabular-nums text-n-100">{value}</dd>
      {hint ? <dd className="mt-0.5 text-tiny text-n-500">{hint}</dd> : null}
    </div>
  )
}

/* ---------------------------------------------------------------- controls */

/* Pills, as Apple and Tsenta both draw them. A rounded rectangle reads as a
   form field; a pill reads as something to press. */
const BUTTON_VARIANT = {
  primary:
    'bg-accent text-n-950 font-medium hover:bg-brand-400 ' +
    'disabled:bg-n-700 disabled:text-n-500',
  secondary:
    'bg-surface text-n-100 border border-line-strong hover:bg-n-850 ' +
    'disabled:bg-n-850 disabled:text-n-500 disabled:border-line',
  ghost:
    'text-n-300 hover:bg-n-850 hover:text-n-100 disabled:text-n-500 ' +
    'disabled:hover:bg-transparent',
  danger:
    'bg-bad-400 text-n-950 font-medium hover:brightness-110 ' +
    'disabled:bg-n-700 disabled:text-n-500',
}

const BUTTON_SIZE = {
  sm: 'h-7 gap-1.5 px-3 text-tiny rounded-full',
  md: 'h-9 gap-2 px-4 text-sm rounded-full',
}

export function Button({
  variant = 'secondary',
  size = 'md',
  busy = false,
  disabled,
  className = '',
  children,
  onClick,
  ...rest
}) {
  // Feedback lands on pointer-down rather than on click. Waiting for the
  // release to acknowledge a press is the single clearest way to make a
  // control feel dead, and it costs nothing to fix.
  const { pressed, handlers } = usePress({ onPress: onClick, disabled: disabled || busy })
  return (
    <button
      disabled={disabled || busy}
      data-pressed={pressed}
      // onClick stays bound for keyboard activation, which never fires a
      // pointer event; usePress commits the pointer path and the two do not
      // both fire for one interaction.
      onClick={(event) => {
        if (event.detail === 0) onClick?.(event)
      }}
      {...handlers}
      className={`press inline-flex shrink-0 items-center justify-center whitespace-nowrap
        disabled:cursor-not-allowed ${BUTTON_SIZE[size]} ${BUTTON_VARIANT[variant]} ${className}`}
      {...rest}
    >
      {busy ? <Spinner /> : null}
      {children}
    </button>
  )
}

function Spinner({ className = 'size-3.5' }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

/** Shared by input, select and textarea so the three can never drift. */
/* Fields are the one place that keeps a rounded rectangle rather than a pill:
   a pill-shaped text input tells you it is a button. Focus is the blue ring
   Apple puts on every field, not a border colour change. */
const control =
  'w-full rounded-sm border border-line-strong bg-surface px-3 py-1.5 text-sm text-n-100 ' +
  'transition-[border-color,box-shadow] outline-none placeholder:text-n-500 ' +
  'hover:border-n-500 focus:border-blue-500 focus:ring-[3px] focus:ring-blue-500/18 ' +
  'disabled:bg-n-850 disabled:text-n-500'

export function Input({ className = '', ...rest }) {
  return <input className={`${control} ${className}`} {...rest} />
}

export function Select({ className = '', children, ...rest }) {
  return (
    <select className={`${control} h-8 py-0 ${className}`} {...rest}>
      {children}
    </select>
  )
}

export function Textarea({ className = '', ...rest }) {
  return <textarea className={`${control} resize-y ${className}`} {...rest} />
}

export function Field({ label, hint, htmlFor, children }) {
  // The label is wired to its control automatically rather than every caller
  // remembering an id. Without this the labels are decoration: clicking one
  // focuses nothing, and a screen reader announces the input unnamed. Callers
  // that pass `htmlFor` or set their own id keep them.
  const auto = useId()
  const single = isValidElement(children) ? children : null
  const id = htmlFor || single?.props?.id || auto
  const described = hint ? `${id}-hint` : undefined

  return (
    <div>
      <label
        htmlFor={id}
        className="mb-1 block text-micro font-medium tracking-wide text-n-400 uppercase"
      >
        {label}
      </label>
      {single
        ? cloneElement(single, {
            id,
            'aria-describedby': described || single.props['aria-describedby'],
          })
        : children}
      {hint ? (
        <p id={described} className="mt-1 text-tiny leading-relaxed text-n-500">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

export function Checkbox({ checked, onChange, label, hint, disabled }) {
  return (
    <label className={`flex gap-2.5 ${disabled ? 'opacity-50' : 'cursor-pointer'}`}>
      <input
        type="checkbox"
        checked={!!checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 size-4 shrink-0 accent-blue-500"
      />
      <span className="min-w-0">
        <span className="block text-sm leading-snug text-n-200">{label}</span>
        {hint ? <span className="mt-0.5 block text-tiny leading-relaxed text-n-500">{hint}</span> : null}
      </span>
    </label>
  )
}

/** Switch: for settings that take effect immediately. Anything that needs a
 *  Save button should be a Checkbox instead — the affordance should tell the
 *  user whether the change is already live. */
export function Switch({ checked, onChange, label, hint, disabled }) {
  return (
    <label className={`flex gap-2.5 ${disabled ? 'opacity-50' : 'cursor-pointer'}`}>
      <button
        type="button"
        role="switch"
        aria-checked={!!checked}
        aria-label={typeof label === 'string' ? label : undefined}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        // Apple's switch, at web scale: a grey track that turns green, and a
        // white knob that keeps its own small shadow so it reads as a physical
        // thing sitting in a groove rather than a coloured rectangle.
        className={`mt-px h-[22px] w-[38px] shrink-0 rounded-full p-[2px]
          transition-colors duration-200 ease-out
          ${checked ? 'bg-ok-400' : 'bg-n-700'} ${disabled ? 'cursor-not-allowed' : ''}`}
      >
        <span
          className={`block size-[18px] rounded-full bg-white shadow-[0_1px_2px_rgba(0,0,0,0.2)]
            transition-transform duration-200 ease-out
            ${checked ? 'translate-x-4' : 'translate-x-0'}`}
        />
      </button>
      <span className="min-w-0">
        <span className="block text-sm leading-snug text-n-200">{label}</span>
        {hint ? <span className="mt-0.5 block text-tiny leading-relaxed text-n-500">{hint}</span> : null}
      </span>
    </label>
  )
}

/* ------------------------------------------------------------ status marks */

/** Status text, not a pill. Colour carries the state; the dot gives it a
 *  non-colour cue. Bordered badges on every row were the main source of the
 *  old visual noise. */
const STATUS_COLOR = {
  neutral: 'text-n-400',
  ok: 'text-ok-400',
  warn: 'text-warn-400',
  bad: 'text-bad-400',
  info: 'text-info-400',
  accent: 'text-blue-500',
}

export function Status({ tone = 'neutral', dot = true, pulse = false, title, children }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full
        px-2 py-0.5 text-micro font-medium ${STATUS_CHIP[tone] || STATUS_CHIP.neutral}`}
    >
      {dot ? (
        <span
          className={`size-1.5 shrink-0 rounded-full bg-current ${pulse ? 'animate-pulse-dot' : ''}`}
        />
      ) : null}
      {children}
    </span>
  )
}

/* A tinted pill rather than coloured text on the page ground. In a dense
   table the fill is what carries the meaning at a glance; the word only
   confirms it. */
const STATUS_CHIP = {
  ok: 'bg-ok-tint text-ok-400',
  warn: 'bg-warn-tint text-warn-400',
  bad: 'bg-bad-tint text-bad-400',
  info: 'bg-info-tint text-info-400',
  accent: 'bg-accent-tint text-n-100',
  neutral: 'bg-n-850 text-n-400',
}

/** For categorical values (a role category, a portal name) — never status. */
export function Tag({ children, title, className = '' }) {
  return (
    <span
      title={title}
      className={`inline-block rounded-full bg-n-850 px-2 py-0.5 text-micro text-n-400 ${className}`}
    >
      {children}
    </span>
  )
}

const NOTE_TONE = {
  info: 'border-line bg-info-tint text-n-200',
  warn: 'border-warn-400/25 bg-warn-tint text-n-200',
  bad: 'border-bad-400/25 bg-bad-tint text-n-200',
  ok: 'border-ok-400/25 bg-ok-tint text-n-200',
}

export function Note({ tone = 'info', title, children, onDismiss }) {
  return (
    <div className={`flex items-start gap-3 rounded-sm border px-3 py-2.5 text-sm ${NOTE_TONE[tone]}`}>
      <div className="min-w-0 flex-1">
        {title ? <p className="font-medium">{title}</p> : null}
        <div className={`leading-relaxed ${title ? 'mt-0.5 opacity-85' : ''}`}>{children}</div>
      </div>
      {onDismiss ? (
        <button
          onClick={onDismiss}
          aria-label="Dismiss"
          className="-m-1 shrink-0 rounded-xs p-1 opacity-60 transition-opacity hover:opacity-100"
        >
          <Icon.X className="size-3.5" />
        </button>
      ) : null}
    </div>
  )
}

export function Empty({ title, children, action }) {
  return (
    <div className="px-4 py-12 text-center">
      <p className="text-sm text-n-300">{title}</p>
      {children ? (
        <p className="mx-auto mt-1 max-w-sm text-tiny leading-relaxed text-n-500">{children}</p>
      ) : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  )
}

/** Horizontal meter. Used for score components; no animation. */
export function Meter({ label, value, max, detail }) {
  const pct = max ? Math.max(0, Math.min(value / max, 1)) * 100 : 0
  const tone =
    pct >= 85 ? 'bg-ok-400' : pct >= 60 ? 'bg-blue-500' : pct >= 35 ? 'bg-warn-400' : 'bg-bad-400'
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-n-200">{label}</span>
        <span className="shrink-0 text-tiny tabular-nums text-n-400">
          {value}
          <span className="text-n-500"> / {max}</span>
        </span>
      </div>
      <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-n-800">
        <div className={`h-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      {detail ? <p className="mt-1.5 text-tiny leading-relaxed text-n-500">{detail}</p> : null}
    </div>
  )
}

/** The headline number on the Resume screen. Type does the work — the old
 *  animated SVG ring was decoration around a two-digit figure. */
export function ScoreDisplay({ value, band, caption }) {
  const tone =
    value >= 85 ? 'text-ok-400' : value >= 70 ? 'text-blue-500' : value >= 55 ? 'text-warn-400' : 'text-bad-400'
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className={`text-2xl font-semibold tabular-nums ${tone}`}>{Math.round(value)}</span>
        <span className="text-tiny text-n-500">/ 100</span>
        {band ? <span className="ml-1 text-tiny text-n-400">{band}</span> : null}
      </div>
      {caption ? <p className="mt-1 text-tiny leading-relaxed text-n-500">{caption}</p> : null}
    </div>
  )
}

/* ------------------------------------------------------------------ tables */

/** One table primitive. Three screens used to hand-roll their own markup with
 *  slightly different padding, header colour and border handling. */
export function Table({ columns, rows, renderRow, empty, maxHeight = 'max-h-[32rem]' }) {
  if (!rows.length) return empty || null
  return (
    <div className={`${maxHeight} overflow-auto`}>
      {/* Fixed layout, because auto-layout hands width to whichever column has
          the longest unbroken run of text — which squeezed the job title into
          a four-line column while a date sat in a wide one. Columns that
          matter declare a share; the rest divide what is left. */}
      <table className="w-full table-fixed border-collapse text-left text-tiny">
        {/* Uppercase micro headers on a tinted strip: they read as furniture
            rather than as a first row of data. */}
        <thead className="material-thin sticky top-0 z-10 backdrop-saturate-150">
          <tr className="border-b border-line">
            {columns.map((c, i) => (
              <th
                key={i}
                scope="col"
                className={`px-4 py-2.5 text-micro font-medium tracking-wide text-n-500
                  uppercase ${c.className || ''}`}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{rows.map(renderRow)}</tbody>
      </table>
    </div>
  )
}

export const Tr = ({ children, className = '' }) => (
  <tr className={`border-b border-line align-top transition-colors last:border-0
    hover:bg-n-850/70 ${className}`}>
    {children}
  </tr>
)

export const Td = ({ children, className = '' }) => (
  <td className={`px-4 py-3 ${className}`}>{children}</td>
)

/* ------------------------------------------------------------------- icons */

const stroke = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

/** Icons are 14px (size-3.5) inside buttons and 16px (size-4) standalone.
 *  Only glyphs the app actually uses live here. */
export const Icon = {
  Download: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <path d="M12 4v12m0 0 4-4m-4 4-4-4" />
      <path d="M4 18v1a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1" />
    </svg>
  ),
  Doc: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
      <path d="M14 3v5h5" />
    </svg>
  ),
  Refresh: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <path d="M20 11a8 8 0 1 0-.6 4" />
      <path d="M20 5v6h-6" />
    </svg>
  ),
  X: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  ),
  Chevron: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <path d="m9 6 6 6-6 6" />
    </svg>
  ),
  ArrowLeft: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <path d="M19 12H5M12 19l-7-7 7-7" />
    </svg>
  ),
  Menu: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <path d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  ),
  Sidebar: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
    </svg>
  ),
  SidebarCollapse: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
      <path d="m14 9-3 3 3 3" />
    </svg>
  ),
  Grid: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  ),
  List: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
    </svg>
  ),

  /* Navigation. Line icons at a consistent 1.6 weight, sized to sit on the
     same optical baseline as the label beside them. */
  Briefcase: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18" />
    </svg>
  ),
  File: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </svg>
  ),
  Inbox: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <path d="M3 12h5l2 3h4l2-3h5" />
      <path d="M5 5h14l2 7v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5l2-7Z" />
    </svg>
  ),
  Send: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <path d="M21 3 10.5 13.5M21 3l-6.5 18-4-8-8-4L21 3Z" />
    </svg>
  ),
  Home: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <path d="M4 10.5 12 4l8 6.5" />
      <path d="M6 9.8V19a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V9.8" />
    </svg>
  ),
  User: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <circle cx="12" cy="8" r="3.6" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </svg>
  ),
  Gear: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 3v2.2M12 18.8V21M21 12h-2.2M5.2 12H3M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6M18.4 18.4l-1.6-1.6M7.2 7.2 5.6 5.6" />
    </svg>
  ),
  Sliders: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="8" cy="17" r="2" />
    </svg>
  ),
  Reply: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <path d="M9 7 4 12l5 5" />
      <path d="M4 12h9a7 7 0 0 1 7 7v1" />
    </svg>
  ),
  Plus: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  ),
  Search: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  ),
  Bookmark: ({ filled = false, ...p }) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true"
         {...stroke} fill={filled ? 'currentColor' : 'none'} {...p}>
      <path d="M6 4h12a1 1 0 0 1 1 1v15l-7-4-7 4V5a1 1 0 0 1 1-1Z" />
    </svg>
  ),
  Pin: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <path d="M12 21s7-5.5 7-11a7 7 0 1 0-14 0c0 5.5 7 11 7 11Z" />
      <circle cx="12" cy="10" r="2.5" />
    </svg>
  ),
  Coin: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v8M9.5 9.5c0-1 1-1.5 2.5-1.5s2.5.6 2.5 1.6c0 2-5 1-5 3 0 1 1 1.6 2.5 1.6s2.5-.5 2.5-1.5" />
    </svg>
  ),
  Steps: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <path d="M4 19h4v-4h4v-4h4V7h4" />
    </svg>
  ),
  Clock: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4l3 2" />
    </svg>
  ),
  Calendar: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <rect x="4" y="5" width="16" height="16" rx="2" />
      <path d="M4 9h16M8 3v4M16 3v4" />
    </svg>
  ),
  Logo: (p) => (
    <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true" {...p}
         fill="none" stroke="currentColor" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round">
      {/* Three arrows fanning from one nock. Drawn as strokes: a filled
          version collapsed into three bars at 20px. */}
      <path d="M12 20V7m0 0-2.2 2.6M12 7l2.2 2.6" />
      <path d="M6.6 20 8.9 9.3m0 0-2.7 1.5m2.7-1.5.6 3" />
      <path d="M17.4 20 15.1 9.3m0 0 2.7 1.5m-2.7-1.5-.6 3" />
    </svg>
  ),
  Copy: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  ),
  Mail: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </svg>
  ),
  Sparkles: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <path d="m12 3 1.912 5.885L20 12l-6.088 3.115L12 21l-1.912-5.885L4 12l6.088-3.115L12 3Z" />
    </svg>
  ),
  Check: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  ),
  External: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <path d="M15 3h6v6M10 14 21 3" />
    </svg>
  ),
}
