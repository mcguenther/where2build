/**
 * Changing what a map shows without the map jumping.
 *
 * MapLibre cannot swap a raster ground, an overlay or a palette under a
 * running map, so every such change is a new instance. Tearing the old one
 * down first put the page on bare paper for as long as the new tiles took and
 * then let them pop in one by one. Instead the new map is built in an element
 * of its own, laid over the old one and kept invisible until it has drawn --
 * or until a moment has passed, because a switch follows a button press and
 * must not wait on the slowest tile. It then fades in over the picture it
 * replaces. The old map stays underneath until the new one has every tile, so
 * a tile still missing shows the previous ground rather than bare paper. The
 * first map fades in over the paper the same way.
 *
 * The fade itself is the `.map-fade` rule in `base.css`, which also switches it
 * off for anyone who asked the system for less motion.
 */

/** Matches the transition in `base.css`; the old map goes once it has passed.
 *  Short on purpose: a switch follows a button press, and anything slower
 *  reads as the button lagging rather than as the map settling. */
export const FADE_MS = 150;

/* How long a new map may stay invisible. Waiting for `idle` alone took
   0,8-1,2 s per switch here, measured, which reads as a button that did not
   work -- and MapLibre never fires `idle` at all while one tile keeps failing.
   After this long whatever has drawn is shown, and the rest arrives with the
   per-tile fade below, over the old map still lying underneath. */
const PATIENCE_MS = 400;

/* The old map is taken away once the new one is idle; this is the bound for a
   new map that never gets there, so a failing tile cannot keep two WebGL
   contexts alive for good. */
const OVERLAP_MS = 4000;

/** How long a tile that arrives later -- panning, zooming, a slow server --
 *  takes to appear. MapLibre's default is 300 ms, which on a pan reads as the
 *  map trailing behind the hand; none at all is the pop this module exists to
 *  avoid. Passed as the map's `fadeDuration` too, which does the same for
 *  labels on the vector ground. */
export const TILE_FADE_MS = 100;

/** The same style with every raster layer fading its tiles in quickly. */
export function quickTiles(style) {
  return {
    ...style,
    layers: (style.layers || []).map(layer => layer.type === "raster"
      ? { ...layer, paint: { ...layer.paint, "raster-fade-duration": TILE_FADE_MS } }
      : layer)
  };
}

/** A fresh, still invisible element for one map, on top of any before it. */
export function mapLayer(host) {
  const element = document.createElement("div");
  element.className = "map-fade";
  // Inline, because MapLibre's own stylesheet gives every map container
  // `position: relative`, and which of two single-class rules wins would then
  // depend on the order the stylesheets happen to load in.
  element.style.position = "absolute";
  element.style.inset = "0";
  host.appendChild(element);
  return element;
}

/**
 * Show `element` once `map` has drawn, and call `shown` when the fade is over.
 * Returns a function that cancels both, for a map taken away before that.
 *
 * The end of the fade is the element's own `transitionend`, not a timer of the
 * same length: on a busy main thread the transition started 80 ms after the
 * timer did, and the map under it was removed while the new one was at 18 %.
 * The timer stays as the fallback for reduced motion, where there is no
 * transition and so no event.
 */
export function revealWhenDrawn(map, element, shown = () => {}) {
  let timers = [];
  let revealed = false;
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    timers.forEach(clearTimeout);
    element.removeEventListener("transitionend", onEnd);
    shown();
  };
  const onEnd = event => { if (event.target === element) finish(); };
  const reveal = () => {
    if (revealed) return;
    revealed = true;
    timers.forEach(clearTimeout);
    element.addEventListener("transitionend", onEnd);
    element.classList.add("is-shown");
    timers = [setTimeout(finish, FADE_MS + 250)];
  };
  map.once("idle", reveal);
  timers.push(setTimeout(reveal, PATIENCE_MS));
  return () => {
    revealed = finished = true;
    timers.forEach(clearTimeout);
    element.removeEventListener("transitionend", onEnd);
    map.off("idle", reveal);
  };
}

/** Take a map and its element away. A map that never finished starting cannot
 *  always be removed -- its teardown reaches for internals it never created --
 *  and that must not take the component down with it. */
function discard(entry) {
  entry.cancel?.();
  try { entry.map?.remove(); } catch { /* there is nothing left to keep */ }
  entry.element?.remove();
}

/**
 * The map a component shows, and the ones it is fading out.
 *
 * `start` builds the next map over whatever is showing; `retire` hands the
 * current one over to be faded out, and `clear` takes everything away at once,
 * for an unmount or a backdrop that failed.
 */
export class MapStack {
  constructor() {
    this.current = null;
    this.leaving = [];
  }

  /**
   * `create(element)` constructs the map in the element it is given.
   * `ready(map)` runs once that map is both fully faded in and idle -- the
   * moment anything photographing it may take the picture; a map caught half
   * way through its fade is a washed-out one.
   */
  start(host, create, ready = () => {}) {
    const element = mapLayer(host);
    let map;
    try {
      map = create(element);
    } catch (error) {
      element.remove();
      throw error;
    }
    const entry = { map, element, shown: false, idle: false };
    let overlap = null;
    const settle = () => {
      if (this.current !== entry || !entry.shown || !entry.idle) return;
      clearTimeout(overlap);
      this.dropLeaving();
      ready(map);
    };
    map.on("idle", () => { entry.idle = true; settle(); });
    const cancelReveal = revealWhenDrawn(map, element, () => {
      entry.shown = true;
      overlap = setTimeout(() => { if (this.current === entry) this.dropLeaving(); }, OVERLAP_MS);
      settle();
    });
    entry.cancel = () => { cancelReveal(); clearTimeout(overlap); };
    this.current = entry;
    return map;
  }

  /** Every map on screen, the current one last. */
  get maps() {
    return [...this.leaving, this.current].filter(Boolean).map(entry => entry.map);
  }

  /** Keep the current map on screen until the next one has faded in over it. */
  retire() {
    if (!this.current) return;
    // Its own fade must not finish later and clear the stack under the map
    // that is replacing it.
    this.current.cancel?.();
    this.leaving.push(this.current);
    this.current = null;
  }

  dropLeaving() {
    this.leaving.forEach(discard);
    this.leaving = [];
  }

  clear() {
    this.dropLeaving();
    if (this.current) discard(this.current);
    this.current = null;
  }
}
