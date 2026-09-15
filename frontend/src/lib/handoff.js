/**
 * What the start page hands to the wizard.
 *
 * The wizard owns everything that happens after the field: resolving against
 * ALKIS, reading a page, the land value, the neighbouring parcels, the draft.
 * The start page only carries the input there — so it puts it down here and
 * navigates, and the wizard picks it up and does what it would have done had
 * the input been typed into its own first step.
 *
 * Module state, deliberately: a reload is a new intention, and a pasted page
 * is up to 400 000 characters, which has no business in a URL or in storage.
 */
let pending = null;

/** Leave an input for the wizard. `{ resolve }` or `{ read }`, never both. */
export function handOff(input) {
  pending = input;
}

/** Take it — once. A second stage entered later must not run it again. */
export function takeHandoff() {
  const input = pending;
  pending = null;
  return input;
}
