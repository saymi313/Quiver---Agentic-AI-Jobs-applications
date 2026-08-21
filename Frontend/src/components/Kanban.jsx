import { useRef, useState } from 'react'
import { AnimatePresence, motion as m } from 'motion/react'
import { springFor } from '../lib/motion'

/*
  The pipeline as a board you move cards across.

  A dropdown per row changes a stage; a board lets you *push* the card, and the
  gesture is the point. So this follows the fluid-interface rules to the letter:

    * Feedback on pointer-down. The card lifts the instant it is pressed — it
      does not wait for movement to acknowledge the grab.
    * 1:1 tracking that respects the grab offset. The floating card stays under
      the exact point you took hold of, not snapped to its centre; anything else
      breaks the illusion immediately.
    * Pointer capture, so tracking survives the pointer leaving a column, and a
      small movement threshold so a click is still a click.
    * Interruptible by construction — the drag is direct manipulation, never a
      fixed animation — and the drop settles on a spring via layout, so a card
      released into a column glides home rather than snapping.

  The move is optimistic: the card jumps columns at once and the request goes
  out behind it, because a stage change that waits for the network reads as lag.
*/

const SLOP = 6

export default function Kanban({ columns, cards, onMove }) {
  const colRefs = useRef({})
  const [drag, setDrag] = useState(null) // { id, w, h, dx, dy, x, y, over }
  const dragRef = useRef(null)
  dragRef.current = drag

  const byStage = {}
  for (const col of columns) byStage[col.key] = []
  for (const card of cards) (byStage[card.stage] || (byStage[card.stage] = [])).push(card)

  const columnAt = (x, y) => {
    for (const col of columns) {
      const el = colRefs.current[col.key]
      if (!el) continue
      const r = el.getBoundingClientRect()
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return col.key
    }
    return null
  }

  const onPointerDown = (e, card) => {
    if (e.button != null && e.button !== 0) return
    const rect = e.currentTarget.getBoundingClientRect()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    setDrag({
      id: card.id,
      stage: card.stage,
      w: rect.width,
      h: rect.height,
      dx: e.clientX - rect.left, // where along the card it was grabbed
      dy: e.clientY - rect.top,
      x: e.clientX,
      y: e.clientY,
      over: card.stage,
      moved: false,
    })
  }

  const onPointerMove = (e) => {
    const d = dragRef.current
    if (!d) return
    const moved = d.moved || Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > SLOP
    setDrag({ ...d, x: e.clientX, y: e.clientY, over: columnAt(e.clientX, e.clientY), moved })
  }

  const onPointerUp = (e) => {
    const d = dragRef.current
    e.currentTarget.releasePointerCapture?.(e.pointerId)
    if (d?.moved && d.over && d.over !== d.stage) onMove?.(d.id, d.over)
    setDrag(null)
  }

  const dragged = drag && cards.find((c) => c.id === drag.id)

  return (
    <div className="overflow-x-auto">
      <div className="grid min-w-[52rem] grid-cols-5 gap-3">
        {columns.map((col) => {
          const items = byStage[col.key] || []
          const isTarget = drag?.moved && drag.over === col.key && drag.stage !== col.key
          return (
            <div
              key={col.key}
              ref={(el) => (colRefs.current[col.key] = el)}
              className={`rounded-md border p-2 transition-colors ${
                isTarget ? 'border-blue-500 bg-accent-tint' : 'border-line bg-raised'
              }`}
            >
              <div className="flex items-baseline justify-between px-1 pb-2">
                <span className={`text-micro font-semibold tracking-wide uppercase ${COL_TONE[col.tone]}`}>
                  {col.label}
                </span>
                <span className="text-micro tabular-nums text-n-500">{items.length}</span>
              </div>

              <div className="space-y-2">
                <AnimatePresence initial={false}>
                  {items.map((card) => {
                    const hidden = drag?.moved && drag.id === card.id
                    return (
                      <m.article
                        key={card.id}
                        layout
                        layoutId={`card-${card.id}`}
                        transition={springFor()}
                        onPointerDown={(e) => onPointerDown(e, card)}
                        onPointerMove={onPointerMove}
                        onPointerUp={onPointerUp}
                        style={{ touchAction: 'none' }}
                        className={`cursor-grab touch-none rounded-sm border border-line bg-surface
                          p-2.5 shadow-card select-none active:cursor-grabbing ${
                            hidden ? 'opacity-30' : ''
                          }`}
                      >
                        <CardBody card={card} />
                      </m.article>
                    )
                  })}
                </AnimatePresence>
                {!items.length ? (
                  <p className="px-1 py-4 text-center text-micro text-n-500">—</p>
                ) : null}
              </div>
            </div>
          )
        })}
      </div>

      {/* The lifted card: a fixed clone that tracks the pointer 1:1, offset by
          where it was grabbed. Rendered above everything, ignoring pointer
          events so the hit-test underneath still sees the columns. */}
      {dragged && drag ? (
        <div
          className="pointer-events-none fixed z-50 will-change-transform"
          style={{
            left: drag.x - drag.dx,
            top: drag.y - drag.dy,
            width: drag.w,
          }}
        >
          <div className="rotate-[1.5deg] rounded-sm border border-blue-500/40 bg-surface p-2.5
            shadow-pop">
            <CardBody card={dragged} />
          </div>
        </div>
      ) : null}
    </div>
  )
}

const COL_TONE = {
  ok: 'text-ok-400',
  accent: 'text-blue-500',
  bad: 'text-bad-400',
  warn: 'text-warn-400',
  neutral: 'text-n-500',
}

function CardBody({ card }) {
  return (
    <>
      <p className="line-clamp-2 text-tiny font-medium text-n-100">{card.title || 'Untitled role'}</p>
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="truncate text-micro text-n-500">{card.company_name || '—'}</span>
        {card.message_count ? (
          <span className="shrink-0 text-micro tabular-nums text-n-400">
            ✉ {card.message_count}
          </span>
        ) : null}
      </div>
    </>
  )
}
