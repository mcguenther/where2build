/**
 * Changing what a map shows without the map jumping.
 *
 * MapLibre cannot swap a raster ground, an overlay or a palette under a
 * running map, so every such change is a new instance. Tearing the old one
 * down first put the page on bare paper for as long as the new tiles took and
 * then let them pop in one by one. Instead the new map is built in an element
 * of its own, laid over the old one and kept invisible until it has drawn; it
 * then fades in over the picture it replaces, and only after that is the old
 * one removed. The first map fades in over the paper the same way.
 *
 * The fade itself is the `.map-fade` rule in `base.css`, which also switches it
 * off for anyone who asked the system for less motion.
 */

/** Matches the transition in `base.css`; the old map goes once it has passed. */
export const FADE_MS = 420;

/* MapLibre never fires `idle` while one tile keeps failing, so waiting for it
   alone would leave a map with a single 502 invisible forever. After this
   long whatever has drawn is shown, and the rest arrives with MapLibre's own
   per-tile fade. */
const PATIENCE_MS = 2500;

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
 */
export function revealWhenDrawn(map, element, shown = () => {}) {
  let timers = [];
  let done = false;
  const reveal = () => {
    if (done) return;
    done = true;
    timers.forEach(clearTimeout);
    element.classList.add("is-shown");
    timers = [setTimeout(shown, FADE_MS)];
  };
  map.once("idle", reveal);
  timers.push(setTimeout(reveal, PATIENCE_MS));
  return () => {
    done = true;
    timers.forEach(clearTimeout);
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
    const settle = () => {
      if (this.current === entry && entry.shown && entry.idle) ready(map);
    };
    map.on("idle", () => { entry.idle = true; settle(); });
    entry.cancel = revealWhenDrawn(map, element, () => {
      entry.shown = true;
      this.dropLeaving();
      settle();
    });
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
