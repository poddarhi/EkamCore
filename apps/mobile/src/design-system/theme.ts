/**
 * Theme — runtime theme with scaled typography (S16-007 / FS-179).
 *
 * Provides a createScaledTypography function that applies the system
 * font scale to all typography tokens. Used with useScaledSize().
 */

import {Typography} from './tokens';

/**
 * Create a typography object with font sizes scaled by the given multiplier.
 * Clamped at 2x to prevent layout breakage.
 */
export function createScaledTypography(fontScale: number) {
  const s = Math.min(fontScale, 2.0);
  const scale = (size: number) => Math.round(size * s);

  return {
    display: {...Typography.display, fontSize: scale(32), lineHeight: scale(40)},
    h1: {...Typography.h1, fontSize: scale(24), lineHeight: scale(32)},
    h2: {...Typography.h2, fontSize: scale(20), lineHeight: scale(28)},
    h3: {...Typography.h3, fontSize: scale(18), lineHeight: scale(24)},
    body: {...Typography.body, fontSize: scale(15), lineHeight: scale(22)},
    small: {...Typography.small, fontSize: scale(13), lineHeight: scale(18)},
    caption: {...Typography.caption, fontSize: scale(12), lineHeight: scale(16)},
  } as const;
}

/**
 * Animation duration multiplier — set to 0 when reduceMotion is enabled.
 */
export function animationDuration(baseMs: number, reduceMotion: boolean): number {
  return reduceMotion ? 0 : baseMs;
}
