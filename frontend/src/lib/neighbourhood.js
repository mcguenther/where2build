/**
 * What the buildings around a plot mean for it — per building, never per edge.
 *
 * The first version of the neighbour hint deepened the setback of a *whole
 * boundary edge* by `3 − d` for the nearest foreign building. On Lessingweg 44
 * (Mölkau 204) that shrank the envelope from 312,9 to 153,7 m²: Lessingweg 42
 * stands 0,04 m from the boundary but only along 12–28 m of a 47,6 m edge, a
 * garage behind the rear corner counted for three edges at once, and garages
 * count for nothing under § 6 Abs. 8 Nr. 1 SächsBO. So:
 *
 * - The § 6 envelope, `buildableArea(plot.polygon, plot.setbacks)`, is never
 *   changed by a neighbour. § 6 Abs. 2 puts every building's setback area on
 *   its own plot; a neighbour standing too close does not deepen ours.
 * - Each neighbouring building is classified (`own`, `accessory`, `boundary`,
 *   `overlap`, `clear`) and whatever follows from it is drawn *where it
 *   stands*: its own 3 m reach onto us, and the part of our envelope nearer
 *   than 6 m to it — the „6-m-Zone", where both setback areas at their minimum
 *   would overlap (§ 6 Abs. 3). That is a question for the Bauaufsicht, never
 *   an obligation, and the text layer (`neighbourhoodFindings.js`) words it so.
 * - Wall heights are unknown (ALKIS and OSM carry none), so only the 3 m floor
 *   of § 6 Abs. 5 is used, and no height is ever invented — the section data
 *   carries positions only.
 *
 * Everything is local metres around the plot's anchor, `{x, y}`, y north, like
 * the rest of the geometry. Edge indices in the *output* are indices into
 * `plot.polygon` as stored (the same indexing `plot.streetEdge` uses), not into
 * the counter-clockwise copy the maths runs on.
 *
 * Areas bounded by a round buffer (the 3 m reach, the 6-m-Zone) are traced on
 * a grid with marching squares: `GRID_STEP_M` = 4 cm, grown to hold at most
 * `MAX_REGION_CELLS` cells per region. On the Mölkau fixtures the traced areas
 * stay within 0,05 m² of a 1 cm trace (6-m-Zone at Lessingweg 42: 68,15
 * against 68,19 m²; the mock-up's 3 cm trace, simplified harder, said 68,12).
 * The error is the contour cutting corners between grid nodes, so it grows
 * with the step, and on a plot big enough to hit the cap it is reported with
 * the region (`step`). The depths are computed exactly from the outlines,
 * not from the grid.
 */
import {
  polygonArea, polygonEdges, asCounterClockwise, isCounterClockwise, pointInPolygon,
  distanceToSegment, boundingBox, clipToHalfPlane, simplify, buildableArea, rectangleCorners
} from "./geometry.js";
import { toLocal } from "./projection.js";
import { streetNames } from "./streetFront.js";

/** § 6 Abs. 5 SächsBO: 0,4 H, at least 3 m. Only the floor is computable. */
export const MINIMUM_SETBACK_M = 3;

/** Two minimal setback areas side by side. Arithmetic, not a norm. */
export const ZONE_M = 2 * MINIMUM_SETBACK_M;

/** Below this a wall stands *at* the boundary (Grenzbebauung). The cadastre
 *  records walls on the line a few centimetres either side of it. */
export const BOUNDARY_GAP_M = 0.5;

/** Buildings further than this from every boundary are not counted in the
 *  „clear" summary. Beyond it a wall would need to be 62 m high (0,4 H) to
 *  reach us. */
export const REACH_M = 25;

/** § 6 Abs. 8 Nr. 1 SächsBO: an exempt building may be 9 m long per boundary. */
export const ACCESSORY_MAX_LENGTH_M = 9;

/**
 * Largest outline still read as a garage or shed: 9 m along a boundary times
 * a 6 m double-garage depth. ALKIS says neither whether a building has
 * Aufenthaltsräume nor how high its walls are, so size stands in for both; an
 * outline above it is treated as a main building, which shows *more*, never
 * less.
 */
export const ACCESSORY_MAX_AREA_M2 = 54;

/** Half-width of the stretch of street the § 34 band looks along. */
export const BAND_WINDOW_M = 60;

/** Without a function (OSM), an outline below this is more likely a garage
 *  than a house and stays out of the § 34 band. The band only orders, it
 *  never decides, so a wrong exclusion costs nothing binding. */
export const BAND_MIN_UNKNOWN_AREA_M2 = 40;

/** Grid for the traced regions, and the cap that keeps a huge plot cheap. */
export const GRID_STEP_M = 0.04;
export const MAX_REGION_CELLS = 250_000;

/** Below this a traced region is noise from the grid, not a zone. */
const MIN_REGION_M2 = 0.01;

/** Intrusions smaller than this are rounding, not a finding. */
const MIN_INTRUSION_M = 0.005;

/** Readings of a Grenzbebauung. „setback" is the cautious default: it never
 *  shows more buildable land than there could be. */
export const READING_SETBACK = "setback";
export const READING_BOUNDARY = "boundary";

/** Building classes, most attention first. */
export const CLASS_BOUNDARY = "boundary";
export const CLASS_OVERLAP = "overlap";
export const CLASS_ACCESSORY = "accessory";
export const CLASS_OWN = "own";
export const CLASS_CLEAR = "clear";

/** Boundary kinds. Left and right as seen from the street, looking in. */
export const BOUNDARY_KINDS = ["street", "right", "rear", "left"];

/* ALKIS function values that describe a garage, shed or other building
   without Aufenthaltsräume. The Grunddatenbestand generalises most of them to
   „Gebäude für Wirtschaft oder Gewerbe", which is why that value is here and
   why a size cap has to sit next to it: the same value covers a workshop. */
const ACCESSORY_USE = /garage|carport|schuppen|gartenhaus|gerätehaus|gewächshaus|nebengebäude|wirtschaft oder gewerbe/i;
const RESIDENTIAL_USE = /wohn/i;

/* ------------------------------------------------------------------------ */
/* Small geometry                                                           */
/* ------------------------------------------------------------------------ */

/** A plain copy of a ring without a repeated closing vertex. Vue proxies cost
 *  a trap per read; see `plainRing` in geometry.js. */
function plainRing(ring) {
  const out = [];
  for (const v of ring ?? []) {
    const p = Array.isArray(v) ? { x: Number(v[0]), y: Number(v[1]) } : { x: Number(v.x), y: Number(v.y) };
    if (Number.isFinite(p.x) && Number.isFinite(p.y)) out.push(p);
  }
  if (out.length > 1) {
    const a = out[0], b = out[out.length - 1];
    if (Math.hypot(a.x - b.x, a.y - b.y) < 1e-6) out.pop();
  }
  return out;
}

/** Area-weighted centroid; the vertex average drifts towards dense corners. */
function centroid(ring) {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < ring.length; i++) {
    const p = ring[i], q = ring[(i + 1) % ring.length];
    const cross = p.x * q.y - q.x * p.y;
    a += cross; cx += (p.x + q.x) * cross; cy += (p.y + q.y) * cross;
  }
  if (Math.abs(a) < 1e-9) {
    return ring.reduce((s, p) => ({ x: s.x + p.x / ring.length, y: s.y + p.y / ring.length }), { x: 0, y: 0 });
  }
  return { x: cx / (3 * a), y: cy / (3 * a) };
}

function segmentsCross(a1, a2, b1, b2) {
  const o = (p, q, r) => Math.sign((q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x));
  const d1 = o(a1, a2, b1), d2 = o(a1, a2, b2), d3 = o(b1, b2, a1), d4 = o(b1, b2, a2);
  return d1 !== d2 && d3 !== d4 && d1 && d2 && d3 && d4;
}

function segmentDistance(a1, a2, b1, b2) {
  if (segmentsCross(a1, a2, b1, b2)) return 0;
  return Math.min(
    distanceToSegment(a1, b1, b2), distanceToSegment(a2, b1, b2),
    distanceToSegment(b1, a1, a2), distanceToSegment(b2, a1, a2)
  );
}

/** Shortest distance between two rings, 0 where they touch, cross or nest. */
export function ringGap(r, q) {
  if (!r.length || !q.length) return Infinity;
  if (pointInPolygon(r[0], q) || pointInPolygon(q[0], r)) return 0;
  let best = Infinity;
  for (let i = 0; i < r.length; i++) {
    const a1 = r[i], a2 = r[(i + 1) % r.length];
    for (let j = 0; j < q.length; j++) {
      const d = segmentDistance(a1, a2, q[j], q[(j + 1) % q.length]);
      if (d < best) { best = d; if (!best) return 0; }
    }
  }
  return best;
}

function distanceToRing(p, ring) {
  let best = Infinity;
  for (let i = 0; i < ring.length; i++) {
    const d = distanceToSegment(p, ring[i], ring[(i + 1) % ring.length]);
    if (d < best) best = d;
  }
  return best;
}

/**
 * The same two measures, precompiled for a grid sweep: a few hundred thousand
 * calls per region, so no object is allocated per call and each segment's
 * direction and length are computed once.
 */
function compileRing(ring) {
  const n = ring.length;
  const ax = new Float64Array(n), ay = new Float64Array(n), dx = new Float64Array(n),
        dy = new Float64Array(n), inv = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const a = ring[i], b = ring[(i + 1) % n];
    ax[i] = a.x; ay[i] = a.y; dx[i] = b.x - a.x; dy[i] = b.y - a.y;
    const l2 = dx[i] * dx[i] + dy[i] * dy[i];
    inv[i] = l2 > 0 ? 1 / l2 : 0;
  }
  const distance = (x, y) => {
    let best = Infinity;
    for (let i = 0; i < n; i++) {
      let t = ((x - ax[i]) * dx[i] + (y - ay[i]) * dy[i]) * inv[i];
      t = t < 0 ? 0 : t > 1 ? 1 : t;
      const ex = x - ax[i] - t * dx[i], ey = y - ay[i] - t * dy[i];
      const d = ex * ex + ey * ey;
      if (d < best) best = d;
    }
    return Math.sqrt(best);
  };
  const inside = (x, y) => {
    let hit = false;
    for (let i = 0; i < n; i++) {
      const yi = ay[i], yj = ay[i] + dy[i];
      if ((yi > y) !== (yj > y) && x < ax[i] + (dx[i] * (y - yi)) / dy[i]) hit = !hit;
    }
    return hit;
  };
  return { distance, signed: (x, y) => (inside(x, y) ? 1 : -1) * distance(x, y) };
}

const boxGap = (a, b) => Math.hypot(
  Math.max(0, a.minX - b.maxX, b.minX - a.maxX),
  Math.max(0, a.minY - b.maxY, b.minY - a.maxY)
);

const growBox = (b, m) => ({ minX: b.minX - m, maxX: b.maxX + m, minY: b.minY - m, maxY: b.maxY + m });

function intersectBoxes(a, b) {
  const box = { minX: Math.max(a.minX, b.minX), maxX: Math.min(a.maxX, b.maxX),
                minY: Math.max(a.minY, b.minY), maxY: Math.min(a.maxY, b.maxY) };
  return box.minX < box.maxX && box.minY < box.maxY ? box : null;
}

/**
 * Where a straight line lies inside a ring, as `[from, to]` intervals in
 * metres from `p0` along `p0 → p1`.
 */
export function lineIntervals(p0, p1, ring) {
  const dx = p1.x - p0.x, dy = p1.y - p0.y, length = Math.hypot(dx, dy);
  if (!(length > 0) || ring.length < 3) return [];
  const ts = [0, 1];
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i], b = ring[(i + 1) % ring.length];
    const ex = b.x - a.x, ey = b.y - a.y;
    const den = dx * ey - dy * ex;
    if (Math.abs(den) < 1e-12) continue;
    const t = ((a.x - p0.x) * ey - (a.y - p0.y) * ex) / den;
    const u = ((a.x - p0.x) * dy - (a.y - p0.y) * dx) / den;
    if (t > 0 && t < 1 && u >= 0 && u <= 1) ts.push(t);
  }
  ts.sort((a, b) => a - b);
  const out = [];
  for (let k = 0; k < ts.length - 1; k++) {
    if (ts[k + 1] - ts[k] < 1e-9) continue;
    const m = (ts[k] + ts[k + 1]) / 2;
    if (!pointInPolygon({ x: p0.x + dx * m, y: p0.y + dy * m }, ring)) continue;
    const from = ts[k] * length, to = ts[k + 1] * length;
    if (out.length && Math.abs(out[out.length - 1][1] - from) < 1e-6) out[out.length - 1][1] = to;
    else out.push([from, to]);
  }
  return out;
}

/**
 * Marching squares over `field(p) > 0` inside `box`. Returns every closed
 * contour and the sum of their areas. `field(x, y, step)`. The regions traced here are a round
 * buffer cut by a parcel or an envelope; they carry no holes, so the areas
 * add up.
 */
function traceRegion(field, box, wantedStep = GRID_STEP_M) {
  const width = box.maxX - box.minX, height = box.maxY - box.minY;
  const cells = (width / wantedStep) * (height / wantedStep);
  const step = cells <= MAX_REGION_CELLS ? wantedStep : wantedStep * Math.sqrt(cells / MAX_REGION_CELLS);
  const cols = Math.ceil(width / step) + 3, rows = Math.ceil(height / step) + 3;
  const x0 = box.minX - step, y0 = box.minY - step;
  const values = new Float64Array(cols * rows);
  /* Two levels. `field` is 1-Lipschitz (a minimum of distances), so a block
     of BLOCK × BLOCK cells whose corners all lie further from zero than the
     block's diagonal plus two cells has one sign throughout, and its inner
     nodes can never be a corner of a crossing cell: they are filled rather
     than computed. Only blocks the contour can pass through are swept at the
     full resolution — about a tenth of the nodes on the Mölkau regions. */
  const BLOCK = 8;
  const margin = BLOCK * step * Math.SQRT2 + 2 * step;
  const coarseCols = Math.ceil((cols - 1) / BLOCK) + 1, coarseRows = Math.ceil((rows - 1) / BLOCK) + 1;
  const coarse = new Float64Array(coarseCols * coarseRows);
  for (let J = 0; J < coarseRows; J++) {
    for (let I = 0; I < coarseCols; I++) {
      coarse[J * coarseCols + I] = field(x0 + I * BLOCK * step, y0 + J * BLOCK * step, step);
    }
  }
  for (let J = 0; J < coarseRows - 1; J++) {
    for (let I = 0; I < coarseCols - 1; I++) {
      const c0 = coarse[J * coarseCols + I], c1 = coarse[J * coarseCols + I + 1];
      const c2 = coarse[(J + 1) * coarseCols + I + 1], c3 = coarse[(J + 1) * coarseCols + I];
      const low = Math.min(c0, c1, c2, c3), high = Math.max(c0, c1, c2, c3);
      const fill = low > margin ? margin : high < -margin ? -margin : 0;
      const jEnd = Math.min(rows - 1, (J + 1) * BLOCK), iEnd = Math.min(cols - 1, (I + 1) * BLOCK);
      for (let j = J * BLOCK; j <= jEnd; j++) {
        const y = y0 + j * step;
        for (let i = I * BLOCK; i <= iEnd; i++) {
          values[j * cols + i] = fill || field(x0 + i * step, y, step);
        }
      }
    }
  }
  let inside = 0;
  for (let k = 0; k < values.length; k++) if (values[k] > 0) inside++;
  if (!inside) return { rings: [], area: 0, step };

  const segments = [];
  const corner = [0, 0, 0, 0];
  const offsets = [[0, 0], [1, 0], [1, 1], [0, 1]];
  for (let j = 0; j < rows - 1; j++) {
    for (let i = 0; i < cols - 1; i++) {
      const v0 = values[j * cols + i], v1 = values[j * cols + i + 1];
      const v2 = values[(j + 1) * cols + i + 1], v3 = values[(j + 1) * cols + i];
      const inner = (v0 > 0) + (v1 > 0) + (v2 > 0) + (v3 > 0);
      if (inner === 0 || inner === 4) continue;
      corner[0] = v0; corner[1] = v1; corner[2] = v2; corner[3] = v3;
      const hits = [];
      for (let k = 0; k < 4; k++) {
        const a = k, b = (k + 1) % 4, va = corner[a], vb = corner[b];
        if ((va > 0) === (vb > 0)) continue;
        const t = va / (va - vb);
        const ax = x0 + (i + offsets[a][0]) * step, ay = y0 + (j + offsets[a][1]) * step;
        const bx = x0 + (i + offsets[b][0]) * step, by = y0 + (j + offsets[b][1]) * step;
        hits.push({ x: ax + t * (bx - ax), y: ay + t * (by - ay) });
      }
      if (hits.length === 2) segments.push(hits);
      else if (hits.length === 4) { segments.push([hits[0], hits[1]]); segments.push([hits[2], hits[3]]); }
    }
  }

  const key = q => `${Math.round(q.x / (step / 8))},${Math.round(q.y / (step / 8))}`;
  const ends = new Map();
  segments.forEach((segment, idx) => {
    for (const end of [0, 1]) {
      const k = key(segment[end]);
      if (!ends.has(k)) ends.set(k, []);
      ends.get(k).push({ idx, end });
    }
  });
  const used = new Uint8Array(segments.length);
  const rings = [];
  for (let start = 0; start < segments.length; start++) {
    if (used[start]) continue;
    used[start] = 1;
    const chain = [segments[start][0], segments[start][1]];
    for (;;) {
      const next = (ends.get(key(chain[chain.length - 1])) || []).find(e => !used[e.idx]);
      if (!next) break;
      used[next.idx] = 1;
      chain.push(segments[next.idx][1 - next.end]);
    }
    if (chain.length < 4) continue;
    const ring = simplify(chain, step * 0.25);
    if (ring.length > 1 && key(ring[0]) === key(ring[ring.length - 1])) ring.pop();
    if (ring.length >= 3 && polygonArea(ring) >= MIN_REGION_M2) rings.push(ring);
  }
  return { rings, area: rings.reduce((s, r) => s + polygonArea(r), 0), step };
}

/* ------------------------------------------------------------------------ */
/* Input                                                                    */
/* ------------------------------------------------------------------------ */

/**
 * The neighbour answer (`/api/neighbours`, ALKIS or OSM) in a plot's metre
 * frame: `{ id, ring, address, use, storeys }`. `use` is the ALKIS function
 * verbatim, or null where the source has none (OSM).
 */
export function localBuildings(answerBuildings, anchor) {
  if (!Array.isArray(answerBuildings) || !anchor) return [];
  return answerBuildings.map((building, index) => ({
    id: String(building.id ?? building.osm_id ?? `gebaeude-${index}`),
    ring: plainRing(toLocal(building.umriss ?? [], anchor)),
    address: building.adresse ?? null,
    use: building.funktion ?? null,
    storeys: building.geschosse ?? null
  })).filter(b => b.ring.length >= 3);
}

/** "residential", "accessory" (a use that can be a garage or shed), "other"
 *  or "unknown" (the source has no function at all). */
export function useKind(use) {
  if (use === null || use === undefined || use === "") return "unknown";
  if (RESIDENTIAL_USE.test(use)) return "residential";
  return ACCESSORY_USE.test(use) ? "accessory" : "other";
}

function normaliseBuildings(buildings) {
  return (Array.isArray(buildings) ? buildings : []).map((b, index) => {
    const bare = Array.isArray(b);
    const ring = plainRing(bare ? b : b?.ring ?? []);
    return {
      id: String(bare ? `gebaeude-${index}` : b.id ?? `gebaeude-${index}`),
      ring,
      address: bare ? null : b.address ?? null,
      use: bare ? null : b.use ?? null
    };
  }).filter(b => b.ring.length >= 3);
}

/* ------------------------------------------------------------------------ */
/* Boundaries                                                               */
/* ------------------------------------------------------------------------ */

const DEG = 180 / Math.PI;
const outwardAngle = e => Math.atan2(-e.dx, e.dy) * DEG;   // outward normal of a CCW edge
const turn = (from, to) => ((to - from + 540) % 360) - 180;

/* A side runs while its outward normal stays within this many degrees of
   square to the street's; beyond it the boundary has turned into the rear. */
const SIDE_CONE_DEG = 50;
/* A stub shorter than this — a tidied corner, a jog of a few decimetres —
   does not end a side. */
const STUB_M = 1.5;

/**
 * Group the counter-clockwise edges into the street, the two sides and the
 * rear. The street group is `plot.streetEdge` plus any neighbour continuing
 * in its direction (a street front bent at a vertex). From each street corner
 * the side runs on while the edges keep facing sideways; whatever is left
 * between the two sides is the rear, however many edges it has. A triangle has
 * no rear; a plot whose side turns straight into the rear gets the rest.
 */
function groupBoundaries(edges, streetIndex) {
  const n = edges.length;
  const base = outwardAngle(edges[streetIndex]);
  const angle = i => turn(base, outwardAngle(edges[i]));
  const at = k => ((k % n) + n) % n;
  const taken = new Set([streetIndex]);
  const street = [streetIndex];
  for (let k = streetIndex + 1; !taken.has(at(k)) && Math.abs(angle(at(k))) < 90 - SIDE_CONE_DEG; k++) {
    street.push(at(k)); taken.add(at(k));
  }
  for (let k = streetIndex - 1; !taken.has(at(k)) && Math.abs(angle(at(k))) < 90 - SIDE_CONE_DEG; k--) {
    street.unshift(at(k)); taken.add(at(k));
  }
  const isSide = (i, sign) => {
    const a = angle(i) * sign;
    return a > 90 - SIDE_CONE_DEG && a < 90 + SIDE_CONE_DEG;
  };
  const run = (startK, stepK, sign) => {
    const out = [];
    for (let k = startK; !taken.has(at(k)); k += stepK) {
      const i = at(k);
      if (isSide(i, sign)) { out.push(i); taken.add(i); continue; }
      // A short jog is only part of the side if the side carries on after it.
      const next = at(k + stepK);
      if (edges[i].length < STUB_M && out.length && !taken.has(next) && isSide(next, sign)) {
        out.push(i); taken.add(i); continue;
      }
      break;
    }
    return out;
  };
  const right = run(street[street.length - 1] + 1, 1, 1);
  const left = run(street[0] - 1, -1, -1).reverse();
  const rear = [];
  for (let k = (right.length ? right[right.length - 1] : street[street.length - 1]) + 1; !taken.has(at(k)); k++) {
    rear.push(at(k)); taken.add(at(k));
  }

  const make = (kind, indices, reverse) => {
    if (!indices.length) return null;
    const ordered = reverse ? [...indices].reverse() : indices;
    const points = reverse
      ? [edges[ordered[0]].b, ...ordered.map(i => edges[i].a)]
      : [edges[ordered[0]].a, ...ordered.map(i => edges[i].b)];
    const parts = [];
    let s = 0;
    for (let k = 0; k < points.length - 1; k++) {
      const a = points[k], b = points[k + 1];
      const length = Math.hypot(b.x - a.x, b.y - a.y);
      parts.push({ a, b, from: s, length, edge: ordered[k] });
      s += length;
    }
    return { kind, ccw: indices, points, parts, length: s };
  };
  /* Measured from the street end: the sides from their street corner, the
     street from the left corner, the rear from the right one — which is the
     ring's own counter-clockwise order everywhere except the left side. */
  return [
    make("street", street, false),
    make("right", right, false),
    make("rear", rear, false),
    make("left", left, true)
  ].filter(Boolean);
}

/** Arc length along a boundary of the point on it nearest to `p`; past either
 *  end the straight extension of the end segment, so a building beyond the
 *  corner reads negative or longer than the boundary. */
function projectOnBoundary(p, boundary) {
  let best = null;
  for (const part of boundary.parts) {
    const dx = part.b.x - part.a.x, dy = part.b.y - part.a.y;
    const t = part.length ? ((p.x - part.a.x) * dx + (p.y - part.a.y) * dy) / (part.length * part.length) : 0;
    const clamped = Math.max(0, Math.min(1, t));
    const q = { x: part.a.x + clamped * dx, y: part.a.y + clamped * dy };
    const d = Math.hypot(p.x - q.x, p.y - q.y);
    if (!best || d < best.d - 1e-9) best = { d, part, t };
  }
  const { part, t } = best;
  const first = part === boundary.parts[0], last = part === boundary.parts[boundary.parts.length - 1];
  const along = first && t < 0 ? t : last && t > 1 ? t : Math.max(0, Math.min(1, t));
  return part.from + along * part.length;
}

function boundaryPointAt(boundary, s) {
  const parts = boundary.parts;
  const part = parts.find(p => s <= p.from + p.length) ?? parts[parts.length - 1];
  const t = part.length ? (s - part.from) / part.length : 0;
  const dx = part.b.x - part.a.x, dy = part.b.y - part.a.y;
  return { point: { x: part.a.x + t * dx, y: part.a.y + t * dy }, part };
}

/* ------------------------------------------------------------------------ */
/* The analysis                                                             */
/* ------------------------------------------------------------------------ */

const CLASS_RANK = { [CLASS_BOUNDARY]: 4, [CLASS_OVERLAP]: 3, [CLASS_ACCESSORY]: 2, [CLASS_CLEAR]: 1 };

function emptyAnalysis(envelope = []) {
  return {
    empty: true,
    parcel: [],
    envelope: { ring: envelope, area: envelope.length ? polygonArea(envelope) : 0 },
    streetEdge: null,
    buildings: [],
    zones: [],
    maybeBuildable: [],
    boundaries: [],
    band: null,
    clear: { count: 0, nearest: null, reach: REACH_M },
    sections: [],
    counts: { own: 0, accessory: 0, boundary: 0, overlap: 0, clear: 0 },
    readings: {}
  };
}

const coreCache = new Map();
const CORE_CACHE_LIMIT = 16;

function coreKey(plot, buildings) {
  const polygon = (plot.polygon ?? []).map(v => `${Number(v.x ?? v[0]).toFixed(2)},${Number(v.y ?? v[1]).toFixed(2)}`).join(";");
  const setbacks = Array.isArray(plot.setbacks) ? plot.setbacks.join(",") : String(plot.setbacks ?? "");
  const outlines = buildings.map(b => {
    const p = b.ring[0];
    return `${b.id}:${b.ring.length}:${p.x.toFixed(2)},${p.y.toFixed(2)}:${b.use ?? ""}:${b.address ?? ""}`;
  }).join("|");
  return `${polygon}#${setbacks}#${plot.streetEdge ?? ""}#${plot.streetFront?.street ?? ""}#${outlines}`;
}

/**
 * The whole neighbourhood of a plot.
 *
 * @param {object} plot  the stored plot: `polygon`, `setbacks`, `streetEdge`,
 *   optionally `streetFront.street` and `lagebezeichnung` (for the § 34 band's
 *   same-street check).
 * @param {Array} buildings  `localBuildings(answer.gebaeude, plot.anchor)`, or
 *   bare rings.
 * @param {{reading?: string|Object<string,string>}} options  „setback" (the
 *   default) or „boundary", for every Grenzbebauung at once or per building id.
 *
 * The geometry is memoised on the plot and the outlines (about 40 ms for
 * Mölkau 204 and 71 outlines on a cold cache); switching the reading costs
 * nothing. The same inputs give the same object back.
 *
 * Returns (all lengths in metres, areas in m², points `{x, y}` local metres):
 *
 *     {
 *       empty,                 // true only without a usable plot polygon
 *       parcel,                // our ring, counter-clockwise
 *       envelope: { ring, area },          // § 6, never changed by a neighbour
 *       streetEdge,            // index into plot.polygon
 *       readings: { [buildingId]: "setback" | "boundary" },   // per Grenzbebauung
 *       buildings: [{
 *         id, address, use,    // use = ALKIS function verbatim, or null
 *         useKind,             // "residential" | "accessory" | "other" | "unknown"
 *         ring, area, centre,
 *         class,               // "own" | "accessory" | "boundary" | "overlap" | "clear"
 *         gap,                 // to our boundary; 0 for own; null beyond REACH_M
 *         toBoundary,          // own buildings only: nearest vertex to our boundary
 *         facing: null | {     // accessory, boundary, overlap
 *           boundary,          // "street" | "right" | "rear" | "left"
 *           edge,              // index into plot.polygon of the nearest edge
 *           gap,
 *           span: { from, to, length },   // along the boundary, from its street end;
 *                                          // may run below 0 or past its length
 *           face: { from, to, length },   // the same, cut to the boundary
 *           beyond                         // metres of span past our corners
 *         },
 *         reach: null | { rings, area, depth, step },   // its 3 m on our plot
 *         zone:  null | { rings, area, depth, depthFromBoundary, step },
 *                              // envelope within 6 m of it; computed for
 *                              // boundary and overlap, whether it applies or not
 *         maybeBuildable: null | { ring, area, length, depth },   // boundary only
 *         reading,             // boundary: "setback" | "boundary"; else null
 *         zoneApplies          // true where the zone is drawn under the reading
 *       }],
 *       zones: [{ buildingId, address, outline, class, rings, area, depth,
 *                 depthFromBoundary, step }],   // the zones that apply
 *       maybeBuildable: [{ buildingId, address, ring, area, length, depth }],
 *       boundaries: [{
 *         kind, edges,         // indices into plot.polygon, in walking order
 *         points, length,      // polyline from the street end
 *         status,              // worst class facing it, "clear" when none
 *         facing: [{ buildingId, class, gap, from, to, faceFrom, faceTo }]
 *       }],
 *       band: null | {         // § 34 orientation; depths square to the street edge
 *         window,              // ± metres along the street
 *         houses: [{ buildingId, address, front, rear, along }],
 *         front: { min, max } | null, rear: { min, max } | null,
 *         own: [{ buildingId, address, useKind, front, rear }],
 *         plot: { front, rear }, envelope: { front, rear } | null,
 *         strip, frontZone     // parcel between those depths, rings or null
 *       },
 *       clear: { count, nearest, reach },   // clear buildings within REACH_M
 *       sections: [{           // one per boundary / overlap building
 *         buildingId, boundary, edge, at, origin, direction, reading,
 *         from, to,            // extent of the cut, 0 = our boundary
 *         ourBoundary, oppositeBoundary, neighbourWall,
 *         neighbour, envelope, reach, zone, maybeBuildable,   // [[from, to], …]
 *         buildings: [{ buildingId, class, intervals }]        // others it cuts
 *       }],
 *       counts: { own, accessory, boundary, overlap, clear }
 *     }
 */
export function analyseNeighbourhood(plot, buildings, options = {}) {
  if (!plot || !Array.isArray(plot.polygon) || plot.polygon.length < 3) return emptyAnalysis();
  const list = normaliseBuildings(buildings);
  const key = coreKey(plot, list);
  let core = coreCache.get(key);
  if (!core) {
    core = { value: computeCore(plot, list), readings: new Map() };
    if (coreCache.size >= CORE_CACHE_LIMIT) coreCache.delete(coreCache.keys().next().value);
    coreCache.set(key, core);
  }
  const readingKey = typeof options.reading === "object" && options.reading
    ? JSON.stringify(Object.entries(options.reading).sort())
    : String(options.reading ?? READING_SETBACK);
  let result = core.readings.get(readingKey);
  if (!result) {
    result = applyReading(core.value, options.reading);
    core.readings.set(readingKey, result);
  }
  return result;
}

function computeCore(plot, buildings) {
  const input = plainRing(plot.polygon);
  const envelope = buildableArea(plot.polygon, plot.setbacks ?? 3);
  if (input.length < 3) return emptyAnalysis(envelope);
  const flipped = !isCounterClockwise(input);
  const ring = asCounterClockwise(input);
  const n = ring.length;
  const edges = polygonEdges(ring);
  // Edge i of the reversed ring is edge n − 2 − i of the stored one.
  const toInput = i => (flipped ? (((n - 2 - i) % n) + n) % n : i);
  const streetStored = Number.isInteger(plot.streetEdge) && plot.streetEdge >= 0 && plot.streetEdge < n
    ? plot.streetEdge : 0;
  const streetCcw = toInput(streetStored);   // the mapping is its own inverse
  const setbackOf = i => {
    // buildableArea reads the depths by counter-clockwise edge; so does this.
    const d = Array.isArray(plot.setbacks) ? Number(plot.setbacks[i]) : Number(plot.setbacks);
    return Number.isFinite(d) ? d : MINIMUM_SETBACK_M;
  };

  const groups = groupBoundaries(edges, streetCcw);
  const groupOfEdge = new Map();
  groups.forEach(g => g.ccw.forEach(i => groupOfEdge.set(i, g)));
  const parcelBox = boundingBox(ring);
  const envelopeBox = envelope.length >= 3 ? boundingBox(envelope) : null;

  const out = buildings.map(b => {
    const box = boundingBox(b.ring);
    const centre = centroid(b.ring);
    const record = {
      id: b.id, address: b.address, use: b.use, useKind: useKind(b.use),
      ring: b.ring, area: polygonArea(b.ring), centre,
      class: CLASS_CLEAR, gap: null, facing: null,
      reach: null, zone: null, maybeBuildable: null
    };
    if (pointInPolygon(centre, ring)) {
      record.class = CLASS_OWN;
      record.gap = 0;
      record.toBoundary = Math.min(...b.ring.map(p => distanceToRing(p, ring)));
      return record;
    }
    if (boxGap(box, parcelBox) > REACH_M) return record;
    record.gap = ringGap(b.ring, ring);
    if (record.gap > REACH_M) { record.gap = null; return record; }
    if (record.gap >= MINIMUM_SETBACK_M) return record;

    // The boundary it faces is the edge it comes closest to — one, never all.
    let nearest = null;
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < b.ring.length; j++) {
        const d = segmentDistance(edges[i].a, edges[i].b, b.ring[j], b.ring[(j + 1) % b.ring.length]);
        if (!nearest || d < nearest.d - 1e-9) nearest = { d, i };
      }
    }
    const group = groupOfEdge.get(nearest.i);
    const along = b.ring.map(p => projectOnBoundary(p, group));
    const from = Math.min(...along), to = Math.max(...along);
    const faceFrom = Math.max(0, from), faceTo = Math.min(group.length, to);
    record.facing = {
      boundary: group.kind,
      edge: toInput(nearest.i),
      gap: record.gap,
      span: { from, to, length: to - from },
      face: { from: faceFrom, to: Math.max(faceFrom, faceTo), length: Math.max(0, faceTo - faceFrom) },
      beyond: Math.max(0, -from) + Math.max(0, to - group.length)
    };
    record._edge = nearest.i;
    record._group = group;

    const accessory = record.useKind === "accessory"
      && record.area <= ACCESSORY_MAX_AREA_M2
      && to - from <= ACCESSORY_MAX_LENGTH_M;
    if (accessory) record.class = CLASS_ACCESSORY;
    else record.class = record.gap < BOUNDARY_GAP_M ? CLASS_BOUNDARY : CLASS_OVERLAP;

    if (record.class === CLASS_BOUNDARY || record.class === CLASS_OVERLAP) {
      record.reach = traceReach(b.ring, box, ring, parcelBox, record.gap);
      record.zone = envelopeBox ? traceZone(b.ring, box, envelope, envelopeBox, record.gap) : null;
      if (record.class === CLASS_BOUNDARY) {
        record.maybeBuildable = stripFacing(ring, edges[nearest.i], b.ring, setbackOf(nearest.i));
      }
    }
    return record;
  });

  const boundaries = groups.map(g => {
    const facing = out.filter(b => b._group === g).map(b => ({
      buildingId: b.id, class: b.class, gap: b.gap,
      from: b.facing.span.from, to: b.facing.span.to,
      faceFrom: b.facing.face.from, faceTo: b.facing.face.to
    })).sort((a, b) => a.from - b.from);
    const worst = facing.reduce((w, f) => (CLASS_RANK[f.class] > CLASS_RANK[w] ? f.class : w), CLASS_CLEAR);
    return {
      kind: g.kind,
      edges: g.ccw.map(toInput),
      points: g.points,
      length: g.length,
      status: worst,
      facing
    };
  });

  const sections = out
    .filter(b => b.class === CLASS_BOUNDARY || b.class === CLASS_OVERLAP)
    .map(b => sectionThrough(b, ring, envelope, out, toInput));

  const clearOnes = out.filter(b => b.class === CLASS_CLEAR && b.gap !== null);
  const counts = { own: 0, accessory: 0, boundary: 0, overlap: 0, clear: 0 };
  out.forEach(b => { counts[b.class] += 1; });

  const band = orientationBand(plot, ring, edges[streetCcw], envelope, out);

  for (const b of out) { delete b._edge; delete b._group; }

  return {
    empty: false,
    parcel: ring,
    envelope: { ring: envelope, area: envelope.length ? polygonArea(envelope) : 0 },
    streetEdge: streetStored,
    buildings: out,
    boundaries,
    band,
    clear: {
      count: clearOnes.length,
      nearest: clearOnes.length ? Math.min(...clearOnes.map(b => b.gap)) : null,
      reach: REACH_M
    },
    sections,
    counts
  };
}

/** The neighbour's own 3 m around its outline, on our side of the boundary. */
function traceReach(outline, outlineBox, parcel, parcelBox, gap) {
  const box = intersectBoxes(growBox(outlineBox, MINIMUM_SETBACK_M), parcelBox);
  if (!box) return null;
  const from = compileRing(outline), within = compileRing(parcel);
  const field = (x, y, step) => {
    const a = MINIMUM_SETBACK_M - from.distance(x, y);
    if (a < -2 * step) return a;
    return Math.min(a, within.signed(x, y));
  };
  const region = traceRegion(field, box);
  if (!region.rings.length) return null;
  return { rings: region.rings, area: region.area, depth: MINIMUM_SETBACK_M - gap, step: region.step };
}

/** The part of our envelope nearer than 6 m to the neighbour's outline. */
function traceZone(outline, outlineBox, envelope, envelopeBox, gap) {
  const box = intersectBoxes(growBox(outlineBox, ZONE_M), envelopeBox);
  if (!box) return null;
  const toEnvelope = ringGap(outline, envelope);
  if (toEnvelope >= ZONE_M) return null;
  const from = compileRing(outline), within = compileRing(envelope);
  const field = (x, y, step) => {
    const a = ZONE_M - from.distance(x, y);
    if (a < -2 * step) return a;
    return Math.min(a, within.signed(x, y));
  };
  const region = traceRegion(field, box);
  if (!region.rings.length) return null;
  return {
    rings: region.rings,
    area: region.area,
    // Exact, from the outlines: how far the 6 m reach passes the envelope's
    // edge, and how far it reaches from our boundary.
    depth: ZONE_M - toEnvelope,
    depthFromBoundary: ZONE_M - gap,
    step: region.step
  };
}

/**
 * Under the reading „an die Grenze darf gebaut werden": our setback strip
 * along the stretch of the facing edge where the neighbour stands. Clipped on
 * that one edge's line — the stretch is where the building is, never the edge.
 */
function stripFacing(parcel, edge, outline, depth) {
  const dir = { x: edge.dx / edge.length, y: edge.dy / edge.length };
  const inward = { x: -dir.y, y: dir.x };
  const along = outline.map(p => (p.x - edge.a.x) * dir.x + (p.y - edge.a.y) * dir.y);
  const from = Math.max(0, Math.min(...along)), to = Math.min(edge.length, Math.max(...along));
  if (!(to > from)) return null;
  const at = t => ({ x: edge.a.x + dir.x * t, y: edge.a.y + dir.y * t });
  let strip = clipToHalfPlane(parcel, at(from), dir);
  strip = clipToHalfPlane(strip, at(to), { x: -dir.x, y: -dir.y });
  strip = clipToHalfPlane(strip, { x: edge.a.x + inward.x * depth, y: edge.a.y + inward.y * depth },
    { x: -inward.x, y: -inward.y });
  strip = clipToHalfPlane(strip, edge.a, inward);
  if (strip.length < 3) return null;
  return { ring: strip, area: polygonArea(strip), length: to - from, depth };
}

/* How far the section reaches past our boundary into the neighbour's side. */
const SECTION_OUTSIDE_M = 20;

/**
 * A cut across the plot through the middle of the stretch a neighbour faces,
 * square to that boundary. Positions only, in metres along the cut: 0 is our
 * boundary, positive runs into our plot, negative into the neighbour's.
 */
function sectionThrough(b, parcel, envelope, all, toInput) {
  const group = b._group;
  const middle = (b.facing.face.from + b.facing.face.to) / 2;
  const { point, part } = boundaryPointAt(group, middle);
  // Inward normal of the stretch; for the reversed left side the ring's own
  // direction is the opposite of the part's.
  let nx = -(part.b.y - part.a.y) / part.length, ny = (part.b.x - part.a.x) / part.length;
  if (group.kind === "left") { nx = -nx; ny = -ny; }
  const across = Math.max(...parcel.map(p => (p.x - point.x) * nx + (p.y - point.y) * ny)) + SECTION_OUTSIDE_M;
  const p0 = { x: point.x - nx * SECTION_OUTSIDE_M, y: point.y - ny * SECTION_OUTSIDE_M };
  const p1 = { x: point.x + nx * across, y: point.y + ny * across };
  const shift = list => list.map(([a, c]) => [a - SECTION_OUTSIDE_M, c - SECTION_OUTSIDE_M]);
  const cut = ring => shift(lineIntervals(p0, p1, ring));
  const cutAll = rings => rings.flatMap(cut).sort((x, y) => x[0] - y[0]);

  const plotSpan = cut(parcel).find(([a, c]) => a <= 0.05 && c > 0.05) ?? null;
  const neighbour = cut(b.ring);
  const nearSide = neighbour.filter(([, c]) => c <= 0.05);
  return {
    buildingId: b.id,
    boundary: group.kind,
    edge: toInput(b._edge),
    at: middle,
    origin: point,
    direction: { x: nx, y: ny },
    from: -SECTION_OUTSIDE_M,
    to: across - SECTION_OUTSIDE_M,
    ourBoundary: 0,
    oppositeBoundary: plotSpan ? plotSpan[1] : null,
    neighbourWall: nearSide.length ? Math.max(...nearSide.map(iv => iv[1])) : null,
    neighbour,
    envelope: envelope.length >= 3 ? cut(envelope) : [],
    reach: b.reach ? cutAll(b.reach.rings) : [],
    zone: b.zone ? cutAll(b.zone.rings) : [],
    maybeBuildable: b.maybeBuildable ? cut(b.maybeBuildable.ring) : [],
    buildings: all
      .filter(o => o.id !== b.id)
      .map(o => ({ buildingId: o.id, class: o.class, intervals: cut(o.ring) }))
      .filter(o => o.intervals.length)
  };
}

/**
 * The § 34 orientation band: how far behind the street the houses on our
 * side of it stand and how deep they reach. „Our side" is geometric — the
 * building's centre lies on the plot's side of the street edge's line — and
 * within `BAND_WINDOW_M` along it; where both the plot's street and the
 * building's address name a street, they have to agree, which keeps the
 * houses of the street behind out. Depths are square to the street edge
 * extended. Orientation for „Einfügen", never a limit.
 */
function orientationBand(plot, ring, street, envelope, buildings) {
  if (!street || !(street.length > 0)) return null;
  const dir = { x: street.dx / street.length, y: street.dy / street.length };
  const inward = { x: -dir.y, y: dir.x };
  const mid = { x: (street.a.x + street.b.x) / 2, y: (street.a.y + street.b.y) / 2 };
  const depthOf = p => (p.x - street.a.x) * inward.x + (p.y - street.a.y) * inward.y;
  const alongOf = p => (p.x - mid.x) * dir.x + (p.y - mid.y) * dir.y;
  const ours = new Set([
    ...(plot.streetFront?.street ? streetNames(plot.streetFront.street) : []),
    ...(!plot.streetFront?.street ? streetNames(plot.lagebezeichnung) : [])
  ]);
  /* An address is what ties a building to the street it fronts. ALKIS gives
     none to annexes and rear buildings — four residential outlines of
     18–104 m² behind Lessingweg 38–40 — so where the plot's street is known,
     a house without an address on it stays out. Without a known street the
     geometric side rule is all there is. */
  const sameStreet = b => {
    if (!ours.size) return true;
    const theirs = streetNames(b.address);
    return theirs.some(name => ours.has(name));
  };
  const range = r => {
    const ds = r.map(depthOf);
    return { front: Math.min(...ds), rear: Math.max(...ds) };
  };
  const houses = buildings
    .filter(b => b.class !== CLASS_OWN)
    .filter(b => b.useKind === "residential" || (b.useKind === "unknown" && b.area >= BAND_MIN_UNKNOWN_AREA_M2))
    .filter(b => depthOf(b.centre) > 0 && Math.abs(alongOf(b.centre)) <= BAND_WINDOW_M)
    .filter(b => sameStreet(b))
    .map(b => ({ buildingId: b.id, address: b.address, ...range(b.ring), along: alongOf(b.centre) }))
    .sort((a, b) => b.along - a.along);
  const own = buildings.filter(b => b.class === CLASS_OWN)
    .map(b => ({ buildingId: b.id, address: b.address, useKind: b.useKind, ...range(b.ring) }));
  const plotRange = range(ring);
  const envelopeRange = envelope.length >= 3 ? range(envelope) : null;
  if (!houses.length) {
    return { window: BAND_WINDOW_M, houses: [], front: null, rear: null, own, plot: plotRange,
      envelope: envelopeRange, strip: null, frontZone: null };
  }
  const front = { min: Math.min(...houses.map(h => h.front)), max: Math.max(...houses.map(h => h.front)) };
  const rear = { min: Math.min(...houses.map(h => h.rear)), max: Math.max(...houses.map(h => h.rear)) };
  const between = (from, to) => {
    let r = clipToHalfPlane(ring, { x: street.a.x + inward.x * from, y: street.a.y + inward.y * from }, inward);
    r = clipToHalfPlane(r, { x: street.a.x + inward.x * to, y: street.a.y + inward.y * to }, { x: -inward.x, y: -inward.y });
    return r.length >= 3 ? r : null;
  };
  return {
    window: BAND_WINDOW_M, houses, front, rear, own, plot: plotRange, envelope: envelopeRange,
    strip: between(front.min, rear.max), frontZone: between(front.min, front.max)
  };
}

/** Which reading applies to a Grenzbebauung. */
function readingFor(reading, id) {
  const value = typeof reading === "object" && reading ? reading[id] : reading;
  return value === READING_BOUNDARY ? READING_BOUNDARY : READING_SETBACK;
}

function applyReading(core, reading) {
  if (core.empty) return core;
  const readings = {};
  const buildings = core.buildings.map(b => {
    if (b.class === CLASS_BOUNDARY) {
      const r = readingFor(reading, b.id);
      readings[b.id] = r;
      return { ...b, reading: r, zoneApplies: r === READING_SETBACK && Boolean(b.zone) };
    }
    return { ...b, reading: null, zoneApplies: b.class === CLASS_OVERLAP && Boolean(b.zone) };
  });
  const zones = buildings.filter(b => b.zoneApplies).map(b => ({
    buildingId: b.id, address: b.address, outline: b.ring, class: b.class, ...b.zone
  }));
  const maybeBuildable = buildings
    .filter(b => b.class === CLASS_BOUNDARY && b.reading === READING_BOUNDARY && b.maybeBuildable)
    .map(b => ({ buildingId: b.id, address: b.address, ...b.maybeBuildable }));
  const sections = core.sections.map(s => ({ ...s, reading: readings[s.buildingId] ?? null }));
  return { ...core, buildings, zones, maybeBuildable, sections, readings };
}

/* ------------------------------------------------------------------------ */
/* The house check — runs on every drag                                     */
/* ------------------------------------------------------------------------ */

export const HOUSE_INSIDE = "inside";
export const HOUSE_ZONE = "zone";
export const HOUSE_OUTSIDE = "outside";

const houseCache = new WeakMap();

/**
 * The placed footprint against the envelope and the zones that apply.
 *
 * Intrusion into a zone is `6 m − shortest distance between the footprint and
 * the neighbour's outline`: how far, along the shortest line between the two
 * buildings, our wall stands inside the 6 m. It is exactly the depth by which
 * the footprint would have to move away for the two minimal setback areas to
 * stop overlapping. A footprint in the envelope can only be in a zone through
 * its part nearest the neighbour, so no grid is needed: four edges against an
 * outline, per zone.
 *
 * `placement` is `{cx, cy, width, depth, rotation}` as `rectangleCorners`
 * takes it. Memoised on the analysis object and the placement.
 */
export function checkHouse(analysis, placement) {
  if (!analysis || !placement || ![placement.cx, placement.cy, placement.width, placement.depth]
    .every(Number.isFinite)) return null;
  const key = `${placement.cx},${placement.cy},${placement.width},${placement.depth},${placement.rotation ?? 0}`;
  const last = houseCache.get(analysis);
  if (last && last.key === key) return last.result;

  const corners = rectangleCorners({ ...placement, rotation: placement.rotation ?? 0 });
  const envelope = analysis.envelope?.ring ?? [];
  const outside = envelope.length >= 3 ? corners.filter(p => !pointInPolygon(p, envelope)).length : 4;
  const zones = (analysis.zones ?? [])
    .map(z => ({ buildingId: z.buildingId, address: z.address, intrusion: ZONE_M - ringGap(corners, z.outline) }))
    .filter(z => z.intrusion > MIN_INTRUSION_M)
    .sort((a, b) => b.intrusion - a.intrusion);
  const strips = analysis.maybeBuildable ?? [];
  const outsideCorners = corners.filter(p => envelope.length < 3 || !pointInPolygon(p, envelope));
  const inMaybeBuildable = outsideCorners.length > 0 && strips.length > 0
    && outsideCorners.every(p => strips.some(s => pointInPolygon(p, s.ring)));

  const parcel = analysis.parcel ?? [];
  const result = {
    status: outside ? HOUSE_OUTSIDE : zones.length ? HOUSE_ZONE : HOUSE_INSIDE,
    cornersOutside: outside,
    toBoundary: parcel.length >= 3 ? Math.min(...corners.map(p => distanceToRing(p, parcel))) : null,
    inMaybeBuildable,
    zones,
    corners
  };
  houseCache.set(analysis, { key, result });
  return result;
}
