/*
  Motion primitives.

  Apple describes springs with two designer-facing numbers rather than the
  physics triplet: `damping ratio` (how much it overshoots) and `response` (how
  quickly it reaches the target, in seconds). Motion's spring takes `bounce` and
  `duration`, which map onto those directly — bounce 0 is critically damped.

  Two springs, and only two, so motion across the app is one system:

    ui        damping 1.0, response 0.35 — anything that simply appears,
              resolves or repositions. No overshoot: a panel that bounces open
              because it faded in reads as decoration.
    momentum  damping 0.8, response 0.3  — reserved for motion the user's own
              gesture set going. Overshoot is earned there, never elsewhere.

  Everything here animates transform and opacity only, so the compositor does
  the work, and everything is interruptible: Motion re-targets from the live
  on-screen value rather than restarting from the logical one.
*/

export const SPRING_UI = { type: 'spring', bounce: 0, duration: 0.35 }
export const SPRING_MOMENTUM = { type: 'spring', bounce: 0.2, duration: 0.3 }

/* A cross-fade for people who asked not to be moved. Reduced motion means a
   gentler equivalent, never the absence of feedback. */
export const FADE = { duration: 0.18, ease: [0.33, 0, 0.67, 1] }

export function prefersReducedMotion() {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
  )
}

/* The spring to use for a given interaction, downgraded to a cross-fade when
   the user has asked for reduced motion. Call it at animation time rather than
   at module load, so a change of setting takes effect without a reload. */
export function springFor(kind = 'ui') {
  if (prefersReducedMotion()) return FADE
  return kind === 'momentum' ? SPRING_MOMENTUM : SPRING_UI
}

/*
  Apple's momentum projection, from the Designing Fluid Interfaces sample code.
  Given a release velocity, where would this come to rest? Snap to the target
  nearest *that* point rather than the one nearest the release point, so a flick
  throws the element instead of dropping it.

  Note this is the exponential-decay form, not the v²/(2a) from a physics
  textbook — the two disagree, and this is the one that feels right.
*/
export function project(velocity, decelerationRate = 0.998) {
  return ((velocity / 1000) * decelerationRate) / (1 - decelerationRate)
}

/*
  Progressive resistance past a boundary. A hard stop reads as a frozen
  interface; resistance that grows with the overshoot reads as responsive with
  nothing more to give.
*/
export function rubberband(overshoot, dimension, constant = 0.55) {
  return (overshoot * dimension * constant) / (dimension + constant * Math.abs(overshoot))
}
