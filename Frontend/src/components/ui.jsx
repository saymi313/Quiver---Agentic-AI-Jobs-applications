/*
  The design kit. Every visual decision in the app resolves to something here.

  Conventions:
    * Surfaces are opaque. `surface` is the default panel, `raised` is one
      step up (used for nested blocks), `sunken` is the console well.
    * Depth is a 1px `line` border. No shadows, no blur, no gradients.
    * Radius comes from four tokens; components pick one and never deviate.
    * Type sizes come from the scale in index.css. `micro` is for labels only.
    * Interactive elements define hover / focus / active / disabled together,
      so a new button cannot ship with two of the four.
*/

/* ------------------------------------------------------------------ layout */

/** Page header. Every screen opens with exactly one, so the user always
 *  knows where they are and what the screen is for. */
export function PageHead({ title, description, actions }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4 pb-5">
      <div className="max-w-2xl">
        <h1 className="text-xl font-semibold tracking-tight text-n-100">{title}</h1>
        {description ? (
          <p className="mt-1 text-sm leading-relaxed text-n-400">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  )
}

/** A titled block within a page. Use `flush` when the body is a table or
 *  console that should meet the border with no padding. */
export function Section({ title, description, actions, children, flush = false, className = '' }) {
  return (
    <section className={`rounded-md border border-line bg-surface ${className}`}>
      {title || actions ? (
        <header className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
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
        <div className={flush ? 'border-t border-line' : 'border-t border-line p-4'}>{children}</div>
      ) : null}
    </section>
  )
}

/** Collapsible section. Configuration lives behind these so a screen opens
 *  showing what you came to do, not every knob that governs it. */
export function Disclosure({ title, description, open, onToggle, children, actions }) {
  return (
    <section className="rounded-md border border-line bg-surface">
      <header className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <button
          onClick={() => onToggle(!open)}
          aria-expanded={open}
          className="group flex min-w-0 items-center gap-2 text-left"
        >
          <Icon.Chevron
            className={`size-3.5 shrink-0 text-n-500 transition-transform ${open ? 'rotate-90' : ''}`}
          />
          <span className="min-w-0">
            <span className="block text-sm font-semibold tracking-tight text-n-100 group-hover:text-n-50">
              {title}
            </span>
            {description ? (
              <span className="mt-0.5 block text-tiny text-n-400">{description}</span>
            ) : null}
          </span>
        </button>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </header>
      {open ? <div className="border-t border-line p-4">{children}</div> : null}
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

const BUTTON_VARIANT = {
  primary:
    'bg-accent text-n-950 font-medium hover:bg-brand-400 active:bg-brand-500 ' +
    'disabled:bg-n-700 disabled:text-n-500',
  secondary:
    'bg-raised text-n-200 border border-line-strong hover:bg-n-800 hover:text-n-100 ' +
    'active:bg-n-700 disabled:bg-surface disabled:text-n-600 disabled:border-line',
  ghost:
    'text-n-400 hover:bg-raised hover:text-n-100 active:bg-n-800 disabled:text-n-600 ' +
    'disabled:hover:bg-transparent',
  danger:
    'bg-bad-400 text-n-950 font-medium hover:brightness-110 active:brightness-95 ' +
    'disabled:bg-n-700 disabled:text-n-500',
}

const BUTTON_SIZE = {
  sm: 'h-7 gap-1.5 px-2.5 text-tiny rounded-sm',
  md: 'h-8 gap-2 px-3 text-sm rounded-sm',
}

export function Button({
  variant = 'secondary',
  size = 'md',
  busy = false,
  disabled,
  className = '',
  children,
  ...rest
}) {
  return (
    <button
      disabled={disabled || busy}
      className={`inline-flex shrink-0 items-center justify-center whitespace-nowrap transition-colors
        disabled:cursor-not-allowed ${BUTTON_SIZE[size]} ${BUTTON_VARIANT[variant]} ${className}`}
      {...rest}
    >
      {busy ? <Spinner /> : null}
      {children}
    </button>
  )
}

export function Spinner({ className = 'size-3.5' }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

/** Shared by input, select and textarea so the three can never drift. */
export const control =
  'w-full rounded-sm border border-line-strong bg-sunken px-2.5 py-1.5 text-sm text-n-100 ' +
  'transition-colors outline-none placeholder:text-n-600 ' +
  'hover:border-n-600 focus:border-brand-400 disabled:bg-surface disabled:text-n-500'

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
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1 block text-micro font-medium tracking-wide text-n-400 uppercase"
      >
        {label}
      </label>
      {children}
      {hint ? <p className="mt-1 text-tiny leading-relaxed text-n-500">{hint}</p> : null}
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
        className="mt-0.5 size-3.5 shrink-0 accent-brand-500"
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
        className={`mt-0.5 h-4 w-7 shrink-0 rounded-full p-0.5 transition-colors
          ${checked ? 'bg-accent' : 'bg-n-700'} ${disabled ? 'cursor-not-allowed' : ''}`}
      >
        <span
          className={`block size-3 rounded-full bg-n-100 transition-transform
            ${checked ? 'translate-x-3' : 'translate-x-0'}`}
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
  accent: 'text-brand-400',
}

export function Status({ tone = 'neutral', dot = true, pulse = false, title, children }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap text-tiny ${STATUS_COLOR[tone]}`}
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

/** For categorical values (a role category, a portal name) — never status. */
export function Tag({ children, title, className = '' }) {
  return (
    <span
      title={title}
      className={`inline-block rounded-xs bg-raised px-1.5 py-0.5 text-micro text-n-300 ${className}`}
    >
      {children}
    </span>
  )
}

const NOTE_TONE = {
  info: 'border-line-strong bg-raised text-n-300',
  warn: 'border-warn-400/35 bg-warn-400/8 text-warn-400',
  bad: 'border-bad-400/35 bg-bad-400/8 text-bad-400',
  ok: 'border-ok-400/35 bg-ok-400/8 text-ok-400',
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
    pct >= 85 ? 'bg-ok-400' : pct >= 60 ? 'bg-brand-500' : pct >= 35 ? 'bg-warn-400' : 'bg-bad-400'
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-n-200">{label}</span>
        <span className="shrink-0 text-tiny tabular-nums text-n-400">
          {value}
          <span className="text-n-600"> / {max}</span>
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
    value >= 85 ? 'text-ok-400' : value >= 70 ? 'text-brand-400' : value >= 55 ? 'text-warn-400' : 'text-bad-400'
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
      <table className="w-full border-collapse text-left text-tiny">
        <thead className="sticky top-0 z-10 bg-surface">
          <tr className="border-b border-line">
            {columns.map((c, i) => (
              <th
                key={i}
                scope="col"
                className={`px-3 py-2 font-medium text-n-500 ${c.className || ''}`}
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
  <tr className={`border-b border-line/60 align-top last:border-0 hover:bg-raised/60 ${className}`}>
    {children}
  </tr>
)

export const Td = ({ children, className = '' }) => (
  <td className={`px-3 py-2 ${className}`}>{children}</td>
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
  Play: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" fill="currentColor" aria-hidden="true" {...p}>
      <path d="M8 5.5v13a1 1 0 0 0 1.53.85l10-6.5a1 1 0 0 0 0-1.7l-10-6.5A1 1 0 0 0 8 5.5Z" />
    </svg>
  ),
  Stop: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" fill="currentColor" aria-hidden="true" {...p}>
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  ),
  Download: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <path d="M12 4v12m0 0 4-4m-4 4-4-4" />
      <path d="M4 18v1a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1" />
    </svg>
  ),
  Upload: (p) => (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" {...stroke} {...p}>
      <path d="M12 16V4m0 0L8 8m4-4 4 4" />
      <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
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
  Check: (p) => (
    <svg viewBox="0 0 24 24" className="size-3.5" aria-hidden="true" {...stroke} {...p}>
      <path d="m5 13 4 4L19 7" />
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
}
