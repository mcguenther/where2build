/**
 * Things that open over the page rather than in it.
 *
 * The suggestion list and the reading menu are there while somebody types and
 * gone after. In the flow they pushed everything below them down, and the page
 * jumped with every keystroke; placed absolutely they were cut off by the first
 * ancestor with `overflow: hidden` — `.panel` has one, the start page's
 * reception another. The browser's top layer has neither problem: a popover in
 * it is clipped by nothing and covers everything.
 *
 * Where the Popover API is missing — a test environment, an old browser — the
 * element stays where the template put it and CSS places it absolutely.
 */

/** Whether this browser can put an element into the top layer. */
export const canFloat = () =>
  typeof HTMLElement !== "undefined" && typeof HTMLElement.prototype.showPopover === "function";

/** The largest list a field opens: 19rem at the default font size. */
const MAX_HEIGHT = 304;
/** And the smallest, however little room there is below. */
const MIN_HEIGHT = 160;

/**
 * Where an element opened under `anchor` goes, in viewport pixels.
 *
 * It grows downwards and is capped by the room below, never flipped upwards:
 * a list that jumps above the field when it gets one row too long moves the
 * row under the pointer — the same jolt this exists to prevent.
 *
 * @param {DOMRect} box the anchor's `getBoundingClientRect()`
 * @param {{align?: "left"|"right", width?: number}} options
 *   `width` omitted means: as wide as the anchor.
 */
export function placementUnder(box, { align = "left", width = null } = {}) {
  const room = window.innerHeight - box.bottom - 12;
  const style = {
    top: `${Math.round(box.bottom + 6)}px`,
    maxHeight: `${Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, room))}px`
  };
  if (width === null) {
    style.left = `${Math.round(box.left)}px`;
    style.width = `${Math.round(box.width)}px`;
  } else if (align === "right") {
    // Kept on screen: a marker near the left edge of a phone would otherwise
    // open its menu past the left border of the window.
    style.left = `${Math.max(8, Math.round(box.right - width))}px`;
    style.width = `${width}px`;
  } else {
    style.left = `${Math.round(box.left)}px`;
    style.width = `${width}px`;
  }
  return style;
}

/** Show or hide a popover, ignoring the states the API throws for. */
export function toggleFloating(element, shown) {
  if (!element || !canFloat()) return;
  try {
    const open = element.matches(":popover-open");
    if (shown && !open) element.showPopover();
    if (!shown && open) element.hidePopover();
  } catch {
    /* not connected yet, or already in the wanted state */
  }
}
