/**
 * The Text Size Rule (docs/DESIGN.md, approved): five user-setting steps,
 * all in rem-based rendering — the active step becomes the root font
 * size, so every rem token (spacing included) grows and shrinks with it.
 * Largest (30px) is 200% of Default (15px).
 */

export const TEXT_STEPS =/** @type {const} */ ({
  Small: 14,
  Default: 15,
  Large: 17,
  Larger: 22,
  Largest: 30,
});

/** The px size of a named step; unknown names fall back to Default. */
export function textScale(step) {
  return TEXT_STEPS[step] ?? TEXT_STEPS.Default;
}

/** Names of the five steps, in growing order. */
export function textStepNames() {
  return Object.keys(TEXT_STEPS);
}

/** Largest is 200% of Default (the accessibility floor). */
export function isTwoHundredPercent() {
  return TEXT_STEPS.Largest === TEXT_STEPS.Default * 2;
}

/**
 * Pixels -> rem at the Default root size, shared by the token contract
 * test so the spacing tokens cannot drift from the DESIGN.md px table.
 */
export function DEFAULT_ROOT_PX() {
  return TEXT_STEPS.Default;
}

export function remFromPx(px) {
  return `${Number(px / DEFAULT_ROOT_PX()).toFixed(3).replace(/0+$/, '').replace(/\.$/, '')}rem`;
}
