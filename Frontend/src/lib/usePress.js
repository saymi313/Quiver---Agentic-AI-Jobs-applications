import { useCallback, useRef, useState } from 'react'

/*
  Press feedback that arrives on pointer-down.

  The moment feedback waits for the click event, directness "falls off a cliff":
  a button that only reacts on release feels dead, however fast the handler is.
  So the highlight goes on `pointerdown` and the commit stays on `pointerup`.

  Two details that make it feel like a real control rather than a hover state:

    * Pointer capture, so tracking survives the pointer leaving the element.
    * Hysteresis. Drag more than SLOP away and the press cancels; drag back
      inside and it re-arms. That is what lets someone press a button, think
      better of it, and slide off without firing it.

  Returns props to spread, plus `pressed` for the visual.
*/

const SLOP = 10

export function usePress({ onPress, disabled = false } = {}) {
  const [pressed, setPressed] = useState(false)
  const origin = useRef(null)

  const end = useCallback(
    (event, commit) => {
      if (!origin.current) return
      const { id, inside } = origin.current
      origin.current = null
      setPressed(false)
      try {
        event.currentTarget.releasePointerCapture?.(id)
      } catch {
        /* the pointer was already released; nothing to undo */
      }
      if (commit && inside) onPress?.(event)
    },
    [onPress],
  )

  const handlers = {
    onPointerDown: (event) => {
      if (disabled || event.button !== 0) return
      origin.current = { id: event.pointerId, x: event.clientX, y: event.clientY, inside: true }
      try {
        event.currentTarget.setPointerCapture(event.pointerId)
      } catch {
        /* capture is a nicety, not a requirement */
      }
      setPressed(true)
    },
    onPointerMove: (event) => {
      const start = origin.current
      if (!start) return
      const far =
        Math.abs(event.clientX - start.x) > SLOP || Math.abs(event.clientY - start.y) > SLOP
      if (far === start.inside) {
        start.inside = !far
        setPressed(!far)
      }
    },
    onPointerUp: (event) => end(event, true),
    onPointerCancel: (event) => end(event, false),
    // Keyboard users get the commit through the element's own click/keydown
    // path; this only suppresses a stuck highlight if focus leaves mid-press.
    onBlur: () => {
      origin.current = null
      setPressed(false)
    },
  }

  return { pressed, handlers }
}
