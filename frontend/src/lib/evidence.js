/**
 * How the search map moves.
 *
 * Two rules, and both exist because the first draft broke them.
 *
 * **The camera follows the candidates, not the newest clue.** Framing whatever
 * has just been found hides exactly the parcels that are still possible — a
 * search interface must never stand tighter than its own doubt. So the frame is
 * the live candidate set plus the new evidence, with slack, and a hard minimum
 * half-width so even a confirmed parcel is never shown without its neighbours.
 *
 * **The frame only tightens when a candidate actually drops out.** Otherwise
 * each arriving clue nudges the camera in and out and the map reads as a
 * twitch. Widening is always allowed; narrowing needs a reason.
 *
 * Everything here is pure geometry over `[lon, lat]` — no MapLibre, so it can
 * be tested without a canvas.
 */

/** Metres per degree of latitude. Good to a fraction of a per cent anywhere in Saxony. */
const METRES_PER_DEGREE = 111320;

/** How much air the frame keeps around the candidates. */
export const SLACK = 0.35;

/** Never closer than this, in metres from the centre to the edge.
 *  A 30 m parcel shown alone is a parcel nobody can check. */
export const MIN_HALF_WIDTH_M = 120;

/** How long one camera move takes, and how long a clue stands before the next.
 *
 *  Doubled from the first pass. The camera was arriving before the eye had
 *  followed it — correct on a stopwatch, restless to watch, and the whole
 *  point of pacing a run is that somebody can follow it. */
export const FLIGHT_MS = 1800;
export const DWELL_MS = 2000;

/** The whole backlog has to be played within this, however long it is.
 *
 *  Two seconds a clue is the right pace for evidence arriving live. It is the
 *  wrong pace for a run that is already finished — and most are, because a
 *  search takes a handful of seconds while sixteen clues at two seconds is
 *  half a minute of watching. So the dwell shortens with the backlog: still
 *  one clue at a time, still eased, never a wait.
 *
 *  The budget and the floor doubled with the flight, and they had to: a longer
 *  flight under the old floor is not a calmer camera, it is the same camera
 *  interrupted more often. Sixteen clues now play over twelve seconds instead
 *  of six. */
export const BUDGET_MS = 12000;
export const MIN_DWELL_MS = 480;

/** What a queue of this length may spend per step. */
export const dwellFor = (waiting, dwell = DWELL_MS, budget = BUDGET_MS) =>
  waiting <= 1 ? dwell : Math.max(MIN_DWELL_MS, Math.min(dwell, budget / waiting));

const EMPTY = { west: Infinity, south: Infinity, east: -Infinity, north: -Infinity };

export const isEmptyBounds = bounds =>
  !bounds || !Number.isFinite(bounds.west) || bounds.east < bounds.west;

/** Every `[lon, lat]` in a GeoJSON geometry, however deeply nested. */
export function coordinatesOf(geometry) {
  if (!geometry) return [];
  const out = [];
  const walk = node => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === "number" && typeof node[1] === "number") return void out.push(node);
    node.forEach(walk);
  };
  walk(geometry.coordinates ?? geometry);
  return out;
}

export function boundsOf(geometries) {
  return (Array.isArray(geometries) ? geometries : [geometries])
    .flatMap(coordinatesOf)
    .reduce(
      (box, [lon, lat]) => ({
        west: Math.min(box.west, lon),
        east: Math.max(box.east, lon),
        south: Math.min(box.south, lat),
        north: Math.max(box.north, lat)
      }),
      { ...EMPTY }
    );
}

export function unionBounds(...boxes) {
  return boxes.filter(box => !isEmptyBounds(box)).reduce(
    (a, b) => ({
      west: Math.min(a.west, b.west),
      east: Math.max(a.east, b.east),
      south: Math.min(a.south, b.south),
      north: Math.max(a.north, b.north)
    }),
    { ...EMPTY }
  );
}

/** Whether `inner` lies entirely within `outer` — "the frame is already wide enough". */
export function contains(outer, inner) {
  if (isEmptyBounds(outer) || isEmptyBounds(inner)) return false;
  return (
    outer.west <= inner.west &&
    outer.east >= inner.east &&
    outer.south <= inner.south &&
    outer.north >= inner.north
  );
}

/** Half-width and half-height in metres, for the minimum-size rule. */
export function halfExtentsM(bounds) {
  const lat = (bounds.north + bounds.south) / 2;
  const lonScale = METRES_PER_DEGREE * Math.cos((lat * Math.PI) / 180);
  return {
    x: ((bounds.east - bounds.west) * lonScale) / 2,
    y: ((bounds.north - bounds.south) * METRES_PER_DEGREE) / 2
  };
}

/** Grow a box by a fraction of its own size, and to a minimum half-width. */
export function padBounds(bounds, slack = SLACK, minHalfWidthM = MIN_HALF_WIDTH_M) {
  if (isEmptyBounds(bounds)) return bounds;
  const centreLat = (bounds.north + bounds.south) / 2;
  const centreLon = (bounds.east + bounds.west) / 2;
  const lonScale = METRES_PER_DEGREE * Math.cos((centreLat * Math.PI) / 180);
  const half = halfExtentsM(bounds);
  const x = Math.max(half.x * (1 + slack), minHalfWidthM);
  const y = Math.max(half.y * (1 + slack), minHalfWidthM);
  return {
    west: centreLon - x / lonScale,
    east: centreLon + x / lonScale,
    south: centreLat - y / METRES_PER_DEGREE,
    north: centreLat + y / METRES_PER_DEGREE
  };
}

/**
 * The frame for the next step.
 *
 * `candidates` is what is still possible, `evidence` the geometry of the clue
 * that has just arrived, `previous` where the camera stands now. `tightened`
 * says whether a candidate has actually dropped out — the only thing that
 * licenses moving in.
 */
export function frameFor({ candidates = [], evidence = null, previous = null, tightened = false }) {
  const wanted = padBounds(unionBounds(boundsOf(candidates), boundsOf(evidence)));
  if (isEmptyBounds(wanted)) return previous;
  if (!previous || isEmptyBounds(previous)) return wanted;
  // Widening is always right: something new does not fit. Narrowing is only
  // right once the doubt itself has narrowed.
  if (tightened) return wanted;
  return contains(previous, wanted) ? previous : unionBounds(previous, wanted);
}

/**
 * A layer whose extent dwarfs the frame stops informing and starts tinting.
 *
 * The district wash and the street buffer say something while you can see their
 * shape; once the camera is well inside them they are a colour over everything.
 * Returns an opacity, so the fade is gradual rather than a switch.
 */
export function contextOpacity(layerBounds, frame, { full = 0.9, floor = 0 } = {}) {
  if (isEmptyBounds(layerBounds) || isEmptyBounds(frame)) return floor;
  const layer = halfExtentsM(layerBounds);
  const view = halfExtentsM(frame);
  const ratio = Math.max(layer.x, layer.y) / Math.max(view.x, view.y, 1);
  if (ratio <= 1.5) return full;
  if (ratio >= 6) return floor;
  return floor + (full - floor) * (1 - (ratio - 1.5) / 4.5);
}

/**
 * The queue that paces the incoming clues.
 *
 * Indicia arrive unevenly: the attribute list at once, image recognition after
 * half a second, a model after two. Three arriving together would be a twitch,
 * so each stands for `dwell` and the camera flight gets `flight` to finish.
 * A person clicking in the protocol skips the queue — nobody waits for an
 * animation.
 *
 * The timers are injected so this can be tested without waiting in real time,
 * and `reduced` collapses every wait to nothing for
 * `prefers-reduced-motion: reduce`.
 */
export class StepQueue {
  /* The timers are wrapped rather than referenced: `this.timer = setTimeout`
   * and then `this.timer(…)` calls the native function with the queue as its
   * receiver, which browsers reject with "Illegal invocation" — and the whole
   * run then stops after its first line, with the map still showing Saxony. */
  constructor({
    dwell = DWELL_MS,
    budget = BUDGET_MS,
    reduced = false,
    timer = (fn, ms) => setTimeout(fn, ms),
    cancel = id => clearTimeout(id)
  } = {}) {
    this.dwell = reduced ? 0 : dwell;
    this.budget = budget;
    this.reduced = reduced;
    /* What the current step is actually taking. The camera flight is derived
     * from it, so a fast run does not start a 900 ms flight every 240 ms and
     * spend the whole time interrupting itself. */
    this.step = this.dwell;
    this.timer = timer;
    this.cancel = cancel;
    this.pending = [];
    this.running = false;
    this.handle = null;
    this.onStep = () => {};
    this.onIdle = () => {};
  }

  get waiting() {
    return this.pending.length;
  }

  push(item) {
    this.pending.push(item);
    if (!this.running) this.advance();
  }

  advance() {
    // No dwell means no pacing at all, not a pause of zero: with a timer in
    // between, everything still arrives one turn of the event loop apart, and
    // anything reading the result straight afterwards sees a half-played run.
    if (this.dwell <= 0) return this.flush();
    const next = this.pending.shift();
    if (next === undefined) {
      this.running = false;
      this.onIdle();
      return;
    }
    this.running = true;
    // Recomputed each step: the backlog grows while the stream is open and
    // shrinks as it plays, so the pace follows what is actually waiting.
    this.step = dwellFor(this.pending.length + 1, this.dwell, this.budget);
    this.onStep(next);
    this.handle = this.timer(() => this.advance(), this.step);
  }

  /** Play everything that is queued at once, and stop pacing. */
  flush() {
    if (this.handle !== null) this.cancel(this.handle);
    this.handle = null;
    const rest = this.pending.splice(0);
    rest.forEach(item => this.onStep(item));
    this.running = false;
    this.onIdle();
  }

  stop() {
    if (this.handle !== null) this.cancel(this.handle);
    this.handle = null;
    this.pending = [];
    this.running = false;
  }
}

/** Whether this browser has been asked to keep motion down. */
export const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches);

/**
 * How strongly one clue is drawn.
 *
 * A weak statement covers a large area, a strong one a small area — that is not
 * a metaphor, it is the situation, so both size and opacity carry it: the less
 * certain, the larger and paler. Colour is left free for the source.
 */
export const evidenceOpacity = confidence => 0.12 + 0.5 * Math.min(1, Math.max(0, confidence));
